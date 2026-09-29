"""Migrations are the source of truth for the schema."""
from __future__ import annotations

import pathlib

import pytest

MIGRATIONS = pathlib.Path(__file__).resolve().parent.parent / "migrations"


def test_alembic_ini_does_not_hardcode_a_url():
    """The URL must come from app config, not a second copy in alembic.ini."""
    ini = (MIGRATIONS.parent / "alembic.ini").read_text()
    live = [
        line for line in ini.splitlines()
        if line.strip().startswith("sqlalchemy.url")
    ]
    assert not live, f"alembic.ini must not set sqlalchemy.url, found: {live}"


def test_env_reads_the_url_from_app_config():
    env = (MIGRATIONS / "env.py").read_text()
    assert "get_settings()" in env
    assert "database_url" in env


def test_there_is_exactly_one_head():
    """A branched history would make `upgrade head` ambiguous."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    # Built directly from the script directory: no DATABASE_URL needed, so this
    # structural check runs even with no database available.
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    heads = ScriptDirectory.from_config(cfg).get_heads()
    assert len(heads) == 1, f"expected a single head, got {heads}"


def test_initial_migration_creates_the_trgm_extension():
    """The gin_trgm_ops indexes cannot be built without it."""
    sql = "\n".join(p.read_text() for p in (MIGRATIONS / "versions").glob("*.py"))
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in sql


def test_initial_migration_declares_the_lifecycle_enum():
    sql = "\n".join(p.read_text() for p in (MIGRATIONS / "versions").glob("*.py"))
    for state in ("reported", "matched", "claimed", "closed"):
        assert f'"{state}"' in sql or f"'{state}'" in sql


def test_database_is_stamped_at_head(client):
    """After the fixture migrates, the DB must be at the latest revision."""
    from alembic.script import ScriptDirectory

    from app.db.migrations import alembic_config, current_revision

    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    assert current_revision() == head


def test_no_pending_schema_changes(client):
    """Autogenerate must find nothing: models and migrations agree.

    This is the regression guard -- edit a model without writing a migration and
    this test fails.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext

    from app.db.base import Base
    import app.db.models  # noqa: F401
    from app.db.session import engine

    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)

    # Ignore the alembic_version bookkeeping table, which is not in our metadata.
    diff = [d for d in diff if "alembic_version" not in str(d)]
    assert not diff, f"models drifted from migrations: {diff}"


def test_one_approval_migration_refuses_existing_duplicates(client, auth_headers):
    """uq_claims_one_approved_per_item cannot be built over bad data, and the
    migration says which items are at fault rather than picking a winner."""
    from alembic import command
    from sqlalchemy import text

    from app.db.migrations import alembic_config
    from app.db.session import engine

    owner, a, b = auth_headers(), auth_headers(), auth_headers()
    item = client.post("/items", headers=owner, json={
        "name": "Doubly approved", "description": "Predates the rule",
        "kind": "found", "occurred_on": "2026-08-01"}).json()
    claim_ids = [
        client.post(f"/items/{item['id']}/claims", headers=h,
                    json={"evidence": "mine"}).json()["id"]
        for h in (a, b)
    ]

    cfg = alembic_config()
    command.downgrade(cfg, "b052f2f503ff")
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE claims SET status = 'approved' WHERE id = ANY(:ids)"),
                         {"ids": claim_ids})
        with pytest.raises(RuntimeError, match=rf"item {item['id']} \(2 approved\)"):
            command.upgrade(cfg, "head")
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM items WHERE id = :id"), {"id": item["id"]})
        command.upgrade(cfg, "head")

    from alembic.script import ScriptDirectory

    from app.db.migrations import current_revision

    assert current_revision() == ScriptDirectory.from_config(cfg).get_current_head()
