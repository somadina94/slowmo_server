import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

import bcrypt
import jwt

TokenType = Literal["access", "refresh"]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def generate_otp(length: int = 6) -> str:
    upper = 10**length
    return str(secrets.randbelow(upper)).zfill(length)


def generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_challenge_code(code: str, secret: str) -> str:
    return hmac.new(secret.encode(), code.encode(), hashlib.sha256).hexdigest()


def verify_challenge_code(code: str, hashed: str, secret: str) -> bool:
    return hmac.compare_digest(hash_challenge_code(code, secret), hashed)


def create_token(
    subject: str,
    role: str,
    secret: str,
    token_type: TokenType,
    ttl: timedelta,
    jti: str | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "typ": token_type,
        "jti": jti or uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str, expected_type: TokenType) -> dict[str, Any]:
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    if payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError("unexpected token type")
    return payload


def hash_refresh_jti(jti: str) -> str:
    return bcrypt.hashpw(jti.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_refresh_jti(jti: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(jti.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False
