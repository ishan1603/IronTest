"""Application settings resolved from the environment.

Local development runs on SQLite with no external services. Production sets
DATABASE_URL to Postgres and the same code paths apply, so there is no
dev-only branch to drift out of sync.
"""

from __future__ import annotations

import os
import secrets
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- Core -------------------------------------------------------------
    environment: str = Field(default="development", alias="ENVIRONMENT")
    secret_key: str = Field(default="", alias="SECRET_KEY")

    # -- Database ---------------------------------------------------------
    # Default keeps a fresh clone runnable with no services installed.
    database_url: str = Field(default="sqlite:///./data/irontest.db", alias="DATABASE_URL")

    # -- GitHub OAuth -----------------------------------------------------
    github_client_id: str = Field(default="", alias="GITHUB_CLIENT_ID")
    github_client_secret: str = Field(default="", alias="GITHUB_CLIENT_SECRET")
    github_callback_url: str = Field(
        default="http://localhost:8000/api/auth/github/callback",
        alias="GITHUB_CALLBACK_URL",
    )

    # -- Frontend ---------------------------------------------------------
    frontend_url: str = Field(default="http://localhost:5173", alias="FRONTEND_URL")
    #: Comma-separated additional origins allowed to call the API.
    extra_cors_origins: str = Field(default="", alias="EXTRA_CORS_ORIGINS")

    # -- Sessions ---------------------------------------------------------
    jwt_algorithm: str = "HS256"
    session_ttl_hours: int = Field(default=24 * 14, alias="SESSION_TTL_HOURS")

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        # Render and Heroku hand out postgres:// which SQLAlchemy 2 rejects.
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"production", "prod"}

    @property
    def cors_origins(self) -> list[str]:
        origins = [self.frontend_url.rstrip("/")]
        origins.extend(
            item.strip().rstrip("/")
            for item in self.extra_cors_origins.split(",")
            if item.strip()
        )
        if not self.is_production:
            origins.extend(["http://localhost:5173", "http://127.0.0.1:5173"])
        # Preserve order while removing duplicates.
        return list(dict.fromkeys(origin for origin in origins if origin))

    @property
    def github_oauth_configured(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret)

    def resolved_secret_key(self) -> str:
        """Signing key for sessions and token encryption.

        Production must supply one: generating a key per process would sign
        tokens that every other worker and restart rejects.
        """
        if self.secret_key:
            return self.secret_key
        if self.is_production:
            raise RuntimeError(
                "SECRET_KEY must be set in production. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        return _ephemeral_dev_key()


@lru_cache(maxsize=1)
def _ephemeral_dev_key() -> str:
    """Stable for the life of the process, so dev logins survive reloads."""
    return secrets.token_urlsafe(48)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def sqlite_path(database_url: str) -> str | None:
    """Filesystem path for a SQLite URL, else None."""
    if not database_url.startswith("sqlite"):
        return None
    _, _, tail = database_url.partition("///")
    return os.path.abspath(tail) if tail else None
