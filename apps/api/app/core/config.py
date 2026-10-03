from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "test", "production"] = "development"
    app_name: str = "AI Profit Monitor API"
    database_url: str = (
        "postgresql+asyncpg://ai_profit_monitor:local_development_only@localhost:5437/"
        "ai_profit_monitor"
    )
    cors_origins: list[AnyHttpUrl] = Field(
        default_factory=lambda: [AnyHttpUrl("http://localhost:3000")]
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    session_cookie_name: str = "ai_profit_monitor_session"
    session_lifetime_seconds: int = Field(default=604800, ge=300, le=31536000)
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_cookie_domain: str | None = None
    session_last_used_update_seconds: int = Field(default=300, ge=0, le=86400)
    password_min_length: int = Field(default=12, ge=8, le=128)
    login_rate_limit_attempts: int = Field(default=10, ge=1, le=1000)
    login_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    ingestion_max_batch_size: int = Field(default=100, ge=1, le=1000)
    ingestion_max_body_bytes: int = Field(default=1048576, ge=1024, le=10485760)
    event_max_future_seconds: int = Field(default=300, ge=0, le=86400)
    event_max_age_days: int = Field(default=365, ge=1, le=3650)
    event_page_size: int = Field(default=25, ge=1, le=100)
    event_max_page_size: int = Field(default=100, ge=1, le=500)
    event_max_query_days: int = Field(default=366, ge=1, le=3650)
    api_key_last_used_update_seconds: int = Field(default=300, ge=0, le=86400)

    @field_validator("session_cookie_domain", mode="before")
    @classmethod
    def blank_cookie_domain_is_unset(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @model_validator(mode="after")
    def validate_production_cookie(self) -> Settings:
        if self.app_env == "production" and not self.session_cookie_secure:
            raise ValueError("SESSION_COOKIE_SECURE must be true in production")
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError("SameSite=None cookies must be Secure")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
