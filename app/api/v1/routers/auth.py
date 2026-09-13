from fastapi import APIRouter, Request

from app.core.deps import CurrentUser, DbDep, SettingsDep, get_notifier
from app.core.exceptions import RateLimitError
from app.core.rate_limit import limiter
from app.integrations.notifications import Notifier
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginChallengeOut,
    LoginRequest,
    LogoutRequest,
    MessageOut,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenPair,
    UserOut,
    VerifyLoginRequest,
)
from app.services import auth as auth_service
from fastapi import Depends

router = APIRouter(prefix="/auth", tags=["auth"])


def _guard(request: Request, settings) -> None:
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(f"auth:{ip}", settings.rate_limit_auth):
        raise RateLimitError()


@router.post("/register", response_model=TokenPair)
def register(
    payload: RegisterRequest,
    db: DbDep,
    settings: SettingsDep,
    request: Request,
    notifier: Notifier = Depends(get_notifier),
) -> TokenPair:
    _guard(request, settings)
    pair = auth_service.register(
        db, settings, payload.email, payload.password, payload.name, payload.phone, notifier
    )
    db.commit()
    return pair


@router.post("/login", response_model=LoginChallengeOut)
def login(
    payload: LoginRequest,
    db: DbDep,
    settings: SettingsDep,
    request: Request,
    notifier: Notifier = Depends(get_notifier),
) -> LoginChallengeOut:
    _guard(request, settings)
    result = auth_service.login(db, settings, payload.email, payload.password, notifier, staff_only=False)
    db.commit()
    return result


@router.post("/staff/login", response_model=LoginChallengeOut)
def staff_login(
    payload: LoginRequest,
    db: DbDep,
    settings: SettingsDep,
    request: Request,
    notifier: Notifier = Depends(get_notifier),
) -> LoginChallengeOut:
    _guard(request, settings)
    result = auth_service.login(db, settings, payload.email, payload.password, notifier, staff_only=True)
    db.commit()
    return result


@router.post("/verify-login", response_model=TokenPair)
def verify_login(payload: VerifyLoginRequest, db: DbDep, settings: SettingsDep, request: Request) -> TokenPair:
    _guard(request, settings)
    pair = auth_service.verify_login(db, settings, payload.challenge_id, payload.code)
    db.commit()
    return pair


@router.post("/forgot-password", response_model=MessageOut)
def forgot_password(
    payload: ForgotPasswordRequest,
    db: DbDep,
    settings: SettingsDep,
    request: Request,
    notifier: Notifier = Depends(get_notifier),
) -> MessageOut:
    _guard(request, settings)
    result = auth_service.forgot_password(db, settings, payload.email, notifier)
    db.commit()
    return result


@router.post("/reset-password", response_model=MessageOut)
def reset_password(
    payload: ResetPasswordRequest,
    db: DbDep,
    settings: SettingsDep,
    request: Request,
    notifier: Notifier = Depends(get_notifier),
) -> MessageOut:
    _guard(request, settings)
    result = auth_service.reset_password(db, settings, payload.token, payload.password, notifier)
    db.commit()
    return result


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: DbDep, settings: SettingsDep, request: Request) -> TokenPair:
    _guard(request, settings)
    pair = auth_service.refresh(db, settings, payload.refresh_token)
    db.commit()
    return pair


@router.post("/logout")
def logout(payload: LogoutRequest, db: DbDep, settings: SettingsDep, user: CurrentUser) -> dict:
    count = auth_service.logout(db, settings, payload.refresh_token, user.id)
    db.commit()
    return {"revoked": count}


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
