from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError, ValidationAppError
from app.core.rbac import is_staff
from app.core.security import (
    create_token,
    decode_token,
    generate_otp,
    generate_reset_token,
    hash_challenge_code,
    hash_password,
    hash_refresh_jti,
    verify_challenge_code,
    verify_password,
    verify_refresh_jti,
)
from app.integrations.notifications import Notifier
from app.models.challenge import AuthChallenge
from app.models.token import RefreshToken
from app.models.user import User
from app.repositories import challenges as challenge_repo
from app.repositories import tokens as token_repo
from app.repositories import users as user_repo
from app.schemas.auth import LoginChallengeOut, MessageOut, TokenPair, UserOut


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def initials_for(name: str) -> str:
    parts = [part for part in name.split() if part]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:1].upper()
    return (parts[0][:1] + parts[-1][:1]).upper()


def email_hint(email: str) -> str:
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    visible = local[:1] if local else "*"
    return f"{visible}***@{domain}"


def _pair(settings: Settings, user: User, db: Session) -> TokenPair:
    access = create_token(
        str(user.id),
        user.role,
        settings.jwt_access_secret,
        "access",
        timedelta(minutes=settings.jwt_access_ttl_min),
    )
    refresh = create_token(
        str(user.id),
        user.role,
        settings.jwt_refresh_secret,
        "refresh",
        timedelta(days=settings.jwt_refresh_ttl_days),
    )
    payload = decode_token(refresh, settings.jwt_refresh_secret, "refresh")
    token_repo.add(
        db,
        RefreshToken(
            user_id=user.id,
            jti_hash=hash_refresh_jti(payload["jti"]),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        ),
    )
    return TokenPair(access_token=access, refresh_token=refresh, user=UserOut.model_validate(user))


def _issue_challenge(
    db: Session,
    settings: Settings,
    user: User,
    purpose: str,
    code: str,
    ttl_min: int,
    *,
    public_id: str | None = None,
) -> AuthChallenge:
    challenge_repo.invalidate_open(db, user.id, purpose)
    row = AuthChallenge(
        public_id=public_id or uuid4().hex,
        user_id=user.id,
        purpose=purpose,
        code_hash=hash_challenge_code(code, settings.app_secret_key),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl_min),
    )
    return challenge_repo.add(db, row)


def _load_open_challenge(db: Session, settings: Settings, challenge_id: str, purpose: str) -> AuthChallenge:
    challenge = challenge_repo.get_by_public_id(db, challenge_id)
    if challenge is None or challenge.purpose != purpose or challenge.consumed:
        raise UnauthorizedError("Invalid or expired code")
    if as_utc(challenge.expires_at) < datetime.now(timezone.utc):
        challenge.consumed = True
        raise UnauthorizedError("Invalid or expired code")
    if challenge.attempts >= settings.otp_max_attempts:
        challenge.consumed = True
        raise UnauthorizedError("Too many attempts")
    return challenge


def _consume_with_code(
    db: Session,
    settings: Settings,
    challenge_id: str,
    purpose: str,
    code: str,
) -> AuthChallenge:
    challenge = _load_open_challenge(db, settings, challenge_id, purpose)
    challenge.attempts += 1
    if not verify_challenge_code(code.strip(), challenge.code_hash, settings.app_secret_key):
        raise UnauthorizedError("Invalid or expired code")
    challenge.consumed = True
    return challenge


def register(
    db: Session,
    settings: Settings,
    email: str,
    password: str,
    name: str,
    phone: str = "",
    notifier: Notifier | None = None,
) -> TokenPair:
    if user_repo.get_by_email(db, email):
        raise ConflictError("Email already registered")
    if len(password) < 8:
        raise ValidationAppError("Password must be at least 8 characters")
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        name=name.strip(),
        phone=phone,
        role="customer",
        initials=initials_for(name),
    )
    user_repo.add(db, user)
    if notifier is not None:
        notifier.welcome(user.email, user.name)
    return _pair(settings, user, db)


def login(
    db: Session,
    settings: Settings,
    email: str,
    password: str,
    notifier: Notifier,
    staff_only: bool = False,
) -> LoginChallengeOut:
    user = user_repo.get_by_email(db, email)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise UnauthorizedError("Invalid credentials")
    if staff_only and not is_staff(user.role):
        raise UnauthorizedError("Staff account required")
    code = generate_otp()
    challenge = _issue_challenge(db, settings, user, "login_otp", code, settings.otp_ttl_min)
    notifier.login_otp(user.email, user.name, code)
    return LoginChallengeOut(
        challenge_id=challenge.public_id,
        email_hint=email_hint(user.email),
        debug_code=code if settings.app_debug else None,
    )


def verify_login(db: Session, settings: Settings, challenge_id: str, code: str) -> TokenPair:
    challenge = _consume_with_code(db, settings, challenge_id, "login_otp", code)
    user = user_repo.get_by_id(db, challenge.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid or expired code")
    return _pair(settings, user, db)


def forgot_password(db: Session, settings: Settings, email: str, notifier: Notifier) -> MessageOut:
    message = "If that email is registered, we sent reset instructions."
    user = user_repo.get_by_email(db, email)
    if user is None or not user.is_active:
        return MessageOut(message=message)
    token = generate_reset_token()
    _issue_challenge(
        db,
        settings,
        user,
        "password_reset",
        token,
        settings.reset_ttl_min,
        public_id=token,
    )
    notifier.password_reset(user.email, user.name, token)
    return MessageOut(message=message, debug_token=token if settings.app_debug else None)


def reset_password(
    db: Session,
    settings: Settings,
    token: str,
    password: str,
    notifier: Notifier,
) -> MessageOut:
    if len(password) < 8:
        raise ValidationAppError("Password must be at least 8 characters")
    challenge = _consume_with_code(db, settings, token, "password_reset", token)
    user = user_repo.get_by_id(db, challenge.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid or expired reset link")
    user.password_hash = hash_password(password)
    token_repo.revoke_all(db, user.id)
    notifier.password_changed(user.email, user.name)
    return MessageOut(message="Password updated. You can log in with your new password.")


def refresh(db: Session, settings: Settings, refresh_token: str) -> TokenPair:
    try:
        payload = decode_token(refresh_token, settings.jwt_refresh_secret, "refresh")
    except Exception as exc:
        raise UnauthorizedError("Invalid refresh token") from exc
    user = user_repo.get_by_id(db, int(payload["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError("Invalid refresh token")
    matched = None
    for token in token_repo.list_active_for_user(db, user.id):
        if verify_refresh_jti(payload["jti"], token.jti_hash):
            matched = token
            break
    if matched is None:
        raise UnauthorizedError("Refresh token revoked")
    if as_utc(matched.expires_at) < datetime.now(timezone.utc):
        matched.revoked = True
        raise UnauthorizedError("Refresh token expired")
    matched.revoked = True
    return _pair(settings, user, db)


def logout(db: Session, settings: Settings, refresh_token: str, user_id: int) -> int:
    if not refresh_token:
        return token_repo.revoke_all(db, user_id)
    try:
        payload = decode_token(refresh_token, settings.jwt_refresh_secret, "refresh")
    except Exception:
        return token_repo.revoke_all(db, user_id)
    count = 0
    for token in token_repo.list_active_for_user(db, user_id):
        if verify_refresh_jti(payload["jti"], token.jti_hash):
            token.revoked = True
            count += 1
    return count or token_repo.revoke_all(db, user_id)


def create_staff(db: Session, email: str, password: str, name: str, role: str, phone: str = "") -> User:
    if user_repo.get_by_email(db, email):
        raise ConflictError("Email already registered")
    if role not in {"founder", "ops", "clinician", "admin"}:
        raise ValidationAppError("Invalid staff role")
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        name=name,
        phone=phone,
        role=role,
        initials=initials_for(name),
    )
    return user_repo.add(db, user)


def update_role(db: Session, user_id: int, role: str, actor: User) -> User:
    if role not in {"founder", "ops", "clinician", "admin", "customer"}:
        raise ValidationAppError("Invalid role")
    if role == "founder" and actor.role != "founder":
        raise ForbiddenError("Only a founder can assign the founder role")
    user = user_repo.get_by_id(db, user_id)
    if user is None:
        raise NotFoundError("User not found")
    if user.role == "founder" and role != "founder":
        founders = [row for row in user_repo.list_staff(db) if row.role == "founder"]
        if len(founders) <= 1:
            raise ValidationAppError("Cannot remove the last founder")
    user.role = role
    return user
