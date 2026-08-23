"""Programmatic access to Alembic.

Alembic is the single source of truth for the schema. ``create_all()`` is no
longer used to build a database anywhere in this project -- it survives only as
the model metadata that autogenerate diffs against.
"""
from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import get_settings

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def alembic_config() -> Config:
    """Alembic config pointed at this project, with the app's DATABASE_URL."""
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


def run_migrations(revision: str = "head") -> None:
    """Upgrade the database to ``revision`` (default: latest)."""
    logger.info("Applying Alembic migrations up to %s", revision)
    command.upgrade(alembic_config(), revision)
    logger.info("Migrations applied.")


def current_revision() -> str | None:
    """The revision the database is currently stamped at, if any."""
    from alembic.runtime.migration import MigrationContext

    from app.db.session import engine

    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()
