from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


def env_file_path(app_env: str) -> Path:
    name = "prod" if app_env == "prod" else "dev"
    return ROOT / f".env.{name}"


def normalize_database_url(value: str) -> str:
    url = (value or "").strip().strip("'\"")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    app_env: Literal["dev", "prod"] = "dev"
    app_debug: bool = True
    app_secret_key: str = "dev-secret-change-me"
    database_url: str = "sqlite:///./slowmo.dev.db"
    cors_origins: str = "http://localhost:5011,http://127.0.0.1:5011"
    trusted_hosts: str = "localhost,127.0.0.1"
    jwt_access_secret: str = "dev-access-secret"
    jwt_refresh_secret: str = "dev-refresh-secret"
    jwt_access_ttl_min: int = 30
    jwt_refresh_ttl_days: int = 14
    razorpay_key_id: str = "rzp_test_placeholder"
    razorpay_key_secret: str = "rzp_test_secret_placeholder"
    razorpay_webhook_secret: str = "whsec_dev_placeholder"
    razorpay_webhook_url: str = "http://localhost:5012/api/v1/webhooks/razorpay"
    shipping_provider: Literal["stub"] = "stub"
    storage_backend: Literal["local", "b2"] = "local"
    storage_dir: str = "./storage/rx"
    b2_endpoint: str = ""
    b2_bucket_id: str = ""
    b2_bucket_name: str = ""
    b2_application_key_id: str = ""
    b2_application_key: str = ""
    b2_bucket_region: str = "us-east-005"
    b2_public_file_base_url: str = ""
    mail_backend: Literal["console", "smtp"] = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = "support@jahbyte.com"
    web_app_url: str = "http://localhost:5011"
    seed_founder_email: str = "williams@jahbyte.com"
    seed_founder_password: str = "FounderDev123!"
    rate_limit_auth: int = 30
    rate_limit_webhook: int = 120
    otp_ttl_min: int = 10
    reset_ttl_min: int = 30
    otp_max_attempts: int = 5

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_database_url(value)
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        items = [item.strip().rstrip("/") for item in self.cors_origins.split(",") if item.strip()]
        web = (self.web_app_url or "").strip().rstrip("/")
        if web and web not in items:
            items.append(web)
        # de-dupe, preserve order
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out

    @property
    def trusted_host_list(self) -> list[str]:
        hosts: list[str] = []
        seen: set[str] = set()

        def add(host: str) -> None:
            cleaned = host.strip().lower().split(":")[0]
            if not cleaned or cleaned in seen:
                return
            seen.add(cleaned)
            hosts.append(cleaned)

        for item in self.trusted_hosts.split(","):
            add(item)

        for origin in [*self.cors_origin_list, self.web_app_url, self.razorpay_webhook_url]:
            hostname = urlparse(origin or "").hostname
            if not hostname:
                continue
            add(hostname)
            parts = hostname.split(".")
            if len(parts) >= 2:
                add("*." + ".".join(parts[-2:]))
            if len(parts) >= 3:
                add("*." + ".".join(parts[-3:]))

        add("localhost")
        add("127.0.0.1")
        return hosts

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


def load_settings(
    app_env: str | None = None,
    env_file: Path | None = None,
    **overrides: object,
) -> Settings:
    import os

    resolved_env = app_env or os.getenv("APP_ENV", "dev")
    path = env_file or env_file_path(resolved_env)
    kwargs: dict = {"_env_file": path if path.exists() else None, "app_env": resolved_env}
    kwargs.update(overrides)
    return Settings(**kwargs)


@lru_cache
def get_settings() -> Settings:
    return load_settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
