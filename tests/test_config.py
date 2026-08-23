"""The database URL must be Postgres, and must be present. No fallbacks."""
import pytest

from app.config import Settings


@pytest.mark.parametrize("url", [
    "sqlite:///./site.db",
    "sqlite://",
    "mysql+pymysql://root:pw@localhost/lost_found_db",
    "mongodb://localhost:27017",
])
def test_non_postgres_urls_are_rejected(url):
    with pytest.raises(Exception) as exc:
        Settings(_env_file=None, DATABASE_URL=url, SECRET_KEY="x")
    assert "PostgreSQL" in str(exc.value)


def test_missing_database_url_is_a_startup_error(monkeypatch):
    # Integration fixtures export DATABASE_URL; clear it so this asserts the
    # real "nothing configured" case rather than reading a leftover value.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(Exception) as exc:
        Settings(_env_file=None, SECRET_KEY="x")
    assert "database_url" in str(exc.value).lower() or "DATABASE_URL" in str(exc.value)


@pytest.mark.parametrize("url", [
    "postgresql://u:p@db:5432/lf",
    "postgresql+psycopg://u:p@db:5432/lf",
])
def test_postgres_urls_are_accepted_and_normalised(url):
    settings = Settings(_env_file=None, DATABASE_URL=url, SECRET_KEY="x")
    assert settings.database_url.startswith("postgresql+psycopg://")
