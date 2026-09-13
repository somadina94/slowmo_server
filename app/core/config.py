from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


def env_file_path(app_env: str) -> Path:
    name = "prod" if app_env == "prod" else "dev"
    return ROOT / f".env.{name}"


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

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]

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
