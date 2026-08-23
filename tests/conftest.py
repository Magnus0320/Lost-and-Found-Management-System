"""Test fixtures.

Unit tests (lifecycle, schemas, layering) need no database and always run.
Integration tests need PostgreSQL; they are skipped -- not failed -- when no
TEST_DATABASE_URL is reachable, so `pytest` still collects and passes on a
machine with no database.
"""
from __future__ import annotations

import os
import uuid

import pytest

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://lostfound:lostfound@localhost:5432/lostfound",
)


def _normalise(url: str) -> str:
    """Force the psycopg (v3) driver; a bare postgresql:// URL would resolve to
    psycopg2, which this project does not install."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _database_reachable(url: str) -> bool:
    try:
        import sqlalchemy

        engine = sqlalchemy.create_engine(
            _normalise(url), connect_args={"connect_timeout": 3}
        )
        with engine.connect():
            return True
    except Exception as exc:  # pragma: no cover - diagnostic only
        print(f"[conftest] database unreachable at {url}: {type(exc).__name__}: {exc}")
        return False


@pytest.fixture(scope="session")
def client():
    """TestClient bound to a real Postgres, or skip the whole test."""
    if not _database_reachable(TEST_DB_URL):
        pytest.skip(f"no PostgreSQL reachable at {TEST_DB_URL}")

    os.environ["DATABASE_URL"] = TEST_DB_URL
    os.environ.setdefault("SECRET_KEY", "test-secret-key")
    os.environ["RUN_MIGRATIONS_ON_STARTUP"] = "false"
    os.environ["MAIL_ENABLED"] = "false"

    from app.config import get_settings

    get_settings.cache_clear()

    # Build the schema the same way production does -- by running the Alembic
    # migrations. The suite therefore fails if a migration is broken or missing,
    # rather than silently testing against a create_all() schema that no real
    # deployment ever uses.
    from app.db.migrations import run_migrations
    from app.main import app
    from fastapi.testclient import TestClient

    run_migrations()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    """Register + verify + log in a fresh user; return its bearer header."""

    def _make() -> dict[str, str]:
        tag = uuid.uuid4().hex[:10]
        email = f"user-{tag}@campus.edu"
        password = "correct-horse-battery"
        reg = client.post("/auth/register", json={
            "email": email, "password": password, "first_name": "Test",
            "last_name": "User", "roll_number": f"R{tag[:8]}", "batch": 2026,
            "course": "BTECH", "branch": "CSE"})
        assert reg.status_code == 201, reg.text
        client.post("/auth/verify-registration",
                    json={"email": email, "otp": reg.json()["otp_debug"]})
        token = client.post("/auth/login", json={
            "email": email, "password": password}).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    return _make
