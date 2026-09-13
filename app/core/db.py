from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def make_engine(settings: Settings):
    connect_args = {"check_same_thread": False} if settings.is_sqlite else {}
    return create_engine(settings.database_url, connect_args=connect_args, future=True)


def make_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


_settings = get_settings()
engine = make_engine(_settings)
SessionLocal = make_session_factory(engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
