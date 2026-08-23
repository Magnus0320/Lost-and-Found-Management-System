"""Application settings.

The database URL is intentionally required and intentionally Postgres-only:
there is no SQLite fallback, and a missing or non-Postgres DATABASE_URL is a
startup error rather than a silent downgrade to some other engine.
"""
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_POSTGRES_SCHEMES = (
    "postgresql+psycopg://",
    "postgresql+psycopg2://",
    "postgresql://",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # --- database -------------------------------------------------------
    database_url: str = Field(..., alias="DATABASE_URL")
    db_echo: bool = Field(False, alias="DB_ECHO")
    db_pool_size: int = Field(5, alias="DB_POOL_SIZE")

    # --- auth -----------------------------------------------------------
    secret_key: str = Field(..., alias="SECRET_KEY")
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(720, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    # --- otp / email ----------------------------------------------------
    otp_ttl_minutes: int = Field(10, alias="OTP_TTL_MINUTES")
    mail_from: str = Field("no-reply@campus-lost-found.local", alias="MAIL_FROM")
    mail_server: str | None = Field(None, alias="MAIL_SERVER")
    mail_port: int = Field(587, alias="MAIL_PORT")
    mail_username: str | None = Field(None, alias="MAIL_USERNAME")
    mail_password: str | None = Field(None, alias="MAIL_PASSWORD")
    mail_enabled: bool = Field(False, alias="MAIL_ENABLED")
    # STARTTLS on the submission port (587) is the Gmail path. Set false only
    # for a local test relay that speaks plaintext.
    mail_use_tls: bool = Field(True, alias="MAIL_USE_TLS")
    mail_timeout_seconds: int = Field(15, alias="MAIL_TIMEOUT_SECONDS")

    # --- app ------------------------------------------------------------
    app_name: str = Field("Campus Lost & Found API", alias="APP_NAME")
    environment: str = Field("development", alias="ENVIRONMENT")
    # Schema is owned by Alembic. In containers the entrypoint runs
    # `alembic upgrade head` before the API starts; set this to true only if
    # you want the app process itself to migrate on boot (handy for `uvicorn
    # --reload` during local development).
    run_migrations_on_startup: bool = Field(False, alias="RUN_MIGRATIONS_ON_STARTUP")

    @field_validator("database_url")
    @classmethod
    def _require_postgres(cls, value: str) -> str:
        if not value.startswith(_POSTGRES_SCHEMES):
            raise ValueError(
                "DATABASE_URL must point at PostgreSQL "
                f"(one of {', '.join(_POSTGRES_SCHEMES)}); got {value!r}. "
                "This service has no SQLite/MySQL fallback."
            )
        # Normalise onto the psycopg (v3) driver so a bare postgresql:// URL
        # from docker-compose or a hosting provider still uses the pinned driver.
        if value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
