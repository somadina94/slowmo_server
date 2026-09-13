from pathlib import Path

import jwt
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from app.core.config import env_file_path, load_settings, clear_settings_cache
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, RateLimitError, UnauthorizedError, ValidationAppError
from app.core.headers import SECURITY_HEADERS, SecurityHeadersMiddleware
from app.core.rate_limit import MemoryRateLimiter
from app.core.rbac import has_permission, is_staff, require_any, require_permission
from app.core.security import create_token, decode_token, hash_password, hash_refresh_jti, verify_password, verify_refresh_jti
from datetime import timedelta


def test_env_file_path_variants():
    assert env_file_path("prod").name == ".env.prod"
    assert env_file_path("dev").name == ".env.dev"


def test_load_settings_missing_file(tmp_path: Path):
    settings = load_settings(app_env="dev", env_file=tmp_path / "nope.env", app_secret_key="x")
    assert settings.app_secret_key == "x"
    assert settings.is_sqlite
    assert not settings.is_prod
    assert "localhost" in settings.trusted_host_list or settings.trusted_host_list


def test_load_settings_prod_flags(tmp_path: Path):
    path = tmp_path / ".env.prod"
    path.write_text("APP_ENV=prod\nDATABASE_URL=postgresql+psycopg://u:p@h/db\n")
    settings = load_settings(app_env="prod", env_file=path)
    assert settings.is_prod
    assert not settings.is_sqlite
    clear_settings_cache()


def test_password_and_tokens():
    hashed = hash_password("secret123")
    assert verify_password("secret123", hashed)
    assert not verify_password("nope", hashed)
    assert not verify_password("x", "not-a-hash")
    token = create_token("1", "customer", "sec", "access", timedelta(minutes=5), jti="abc")
    payload = decode_token(token, "sec", "access")
    assert payload["sub"] == "1"
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, "sec", "refresh")
    jti_hash = hash_refresh_jti("abc")
    assert verify_refresh_jti("abc", jti_hash)
    assert not verify_refresh_jti("zzz", jti_hash)
    assert not verify_refresh_jti("abc", "bad")


def test_rbac():
    assert is_staff("founder")
    assert not is_staff("customer")
    assert has_permission("founder", "anything")
    assert has_permission("ops", "orders.write")
    assert not has_permission("clinician", "inventory.write")
    require_permission("admin", "admin.users")
    require_any("ops", ["orders.write", "nope"])
    with pytest.raises(ForbiddenError):
        require_permission("customer", "orders.write")
    with pytest.raises(ForbiddenError):
        require_any("customer", ["orders.write"])


def test_exceptions_status():
    assert UnauthorizedError().status_code == 401
    assert ForbiddenError().status_code == 403
    assert NotFoundError().status_code == 404
    assert ConflictError().status_code == 409
    assert ValidationAppError().status_code == 422
    assert RateLimitError().status_code == 429


def test_rate_limiter():
    limiter = MemoryRateLimiter()
    assert limiter.allow("k", 1)
    assert not limiter.allow("k", 1)
    limiter.reset()
    assert limiter.allow("k", 1)


def test_security_headers_middleware():
    async def homepage(request: Request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[])
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_route("/", homepage)
    client = TestClient(app)
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == SECURITY_HEADERS["X-Content-Type-Options"]
    assert response.headers["X-Frame-Options"] == "DENY"
