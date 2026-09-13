from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.db import SessionLocal, engine as default_engine
from app.core.exceptions import AppError
from app.core.headers import SecurityHeadersMiddleware
from app.models import Base
from app.seed import seed


def make_lifespan(settings: Settings, session_factory: sessionmaker, bind) -> Callable:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        Base.metadata.create_all(bind=bind)
        db = session_factory()
        try:
            seed(db, settings)
        finally:
            db.close()
        yield

    return lifespan


def create_app(
    settings: Settings | None = None,
    bind=None,
    session_factory: sessionmaker | None = None,
) -> FastAPI:
    resolved = settings or get_settings()
    if resolved.is_prod and resolved.is_sqlite:
        raise RuntimeError("DATABASE_URL must be Postgres in production (sqlite is not allowed)")
    resolved_bind = bind if bind is not None else default_engine
    factory = session_factory or SessionLocal
    application = FastAPI(
        title="Slow Mo API",
        version="1.0.0",
        lifespan=make_lifespan(resolved, factory, resolved_bind),
        debug=resolved.app_debug,
    )
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if resolved.is_prod:
        application.add_middleware(TrustedHostMiddleware, allowed_hosts=resolved.trusted_host_list)

    @application.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    application.include_router(api_router, prefix="/api/v1")

    @application.get("/health")
    def health() -> dict:
        return {
            "ok": True,
            "env": resolved.app_env,
            "razorpay_webhook_url": resolved.razorpay_webhook_url,
        }

    return application


app = create_app()
