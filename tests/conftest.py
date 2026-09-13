import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("APP_ENV", "dev")

from app.core.config import Settings, clear_settings_cache, get_settings
from app.core.db import get_db
from app.core.rate_limit import limiter
from app.main import create_app
from app.models import Base
from app.seed import seed


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="dev",
        app_debug=True,
        database_url="sqlite://",
        cors_origins="http://test",
        trusted_hosts="test,testserver",
        jwt_access_secret="test-access",
        jwt_refresh_secret="test-refresh",
        jwt_access_ttl_min=30,
        jwt_refresh_ttl_days=14,
        storage_backend="local",
        storage_dir=str(tmp_path / "rx"),
        mail_backend="console",
        seed_founder_email="meera@slowmo.co",
        seed_founder_password="FounderDev123!",
        rate_limit_auth=1000,
        rate_limit_webhook=1000,
    )


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def db(engine):
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    yield session
    session.close()


@pytest.fixture
def client(settings, engine, db):
    seed(db, settings)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _get_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    application = create_app(settings=settings, bind=engine, session_factory=factory)
    application.dependency_overrides[get_db] = _get_db
    application.dependency_overrides[get_settings] = lambda: settings
    limiter.reset()
    with TestClient(application) as test_client:
        yield test_client
    limiter.reset()
    clear_settings_cache()


def auth_header(client: TestClient, email: str, password: str, staff: bool = False) -> dict:
    path = "/api/v1/auth/staff/login" if staff else "/api/v1/auth/login"
    response = client.post(path, json={"email": email, "password": password})
    body = response.json()
    if body.get("requires_2fa"):
        verified = client.post(
            "/api/v1/auth/verify-login",
            json={"challenge_id": body["challenge_id"], "code": body["debug_code"]},
        )
        token = verified.json()["access_token"]
    else:
        token = body["access_token"]
    return {"Authorization": f"Bearer {token}"}
