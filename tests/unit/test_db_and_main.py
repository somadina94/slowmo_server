from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import pytest

from app.core.config import Settings, get_settings, load_settings, clear_settings_cache
from app.core.db import get_db, make_engine, make_session_factory
from app.main import create_app
from app.models import Base
from app.seed import seed
from app.repositories import catalog as catalog_repo
from app.repositories import orders as order_repo


def test_engine_helpers():
    sqlite = make_engine(Settings(database_url="sqlite://"))
    assert sqlite
    postgres = make_engine(Settings(database_url="postgresql+psycopg://u:p@localhost/db"))
    assert "postgresql" in str(postgres.url)
    factory = make_session_factory(sqlite)
    assert factory
    gen = get_db()
    session = next(gen)
    assert isinstance(session, Session)
    try:
        next(gen)
    except StopIteration:
        pass


def test_get_settings_cache():
    clear_settings_cache()
    first = get_settings()
    second = get_settings()
    assert first is second
    clear_settings_cache()


def test_seed_idempotent(db: Session, settings: Settings):
    seed(db, settings)
    seed(db, settings)
    assert catalog_repo.list_products(db)
    assert catalog_repo.list_programs(db)
    assert catalog_repo.list_products(db, active_only=False)
    assert catalog_repo.list_programs(db, active_only=False)
    assert order_repo.list_all(db, search="SM") == []
    assert order_repo.get_by_id(db, 999) is None
    assert order_repo.get_by_razorpay(db, "none") is None


def test_prod_app_health():
    settings = Settings(
        app_env="prod",
        app_debug=False,
        trusted_hosts="test,testserver",
        cors_origins="http://test",
        seed_founder_email="",
        seed_founder_password="",
        database_url="postgresql+psycopg://u:p@localhost/db",
    )
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    app = create_app(settings=settings, bind=engine, session_factory=factory)
    with TestClient(app, base_url="http://testserver") as client:
        assert client.get("/health").json()["env"] == "prod"


def test_prod_rejects_sqlite():
    settings = Settings(app_env="prod", database_url="sqlite:///./nope.db")
    with pytest.raises(RuntimeError, match="DATABASE_URL must be Postgres"):
        create_app(settings=settings)
