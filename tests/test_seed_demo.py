"""scripts/seed_demo.py -- demo data for a fresh deployment.

The script is run against a live database that may already hold real accounts,
so the two properties that matter are pinned down here: running it again adds
nothing, and --reset removes the demo accounts and nobody else.
"""
import importlib.util
import sys
import uuid
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "seed_demo.py"


def _run(fn):
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        result = fn(db)
        db.commit()
        return result


def _row_counts(db):
    from app.repositories.claim_repo import ClaimRepository
    from app.repositories.item_repo import ItemRepository
    from app.repositories.location_repo import CategoryRepository, LocationRepository
    from app.repositories.user_repo import UserRepository

    return {
        "users": UserRepository(db).count(),
        "items": ItemRepository(db).count(),
        "claims": ClaimRepository(db).count(),
        "locations": LocationRepository(db).list_all()[0],
        "categories": CategoryRepository(db).list_all()[0],
    }


@pytest.fixture
def seed_demo(client, monkeypatch):
    """The script loaded as a module, with demo data cleared before and after."""
    spec = importlib.util.spec_from_file_location("seed_demo", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve their annotations through sys.modules.
    monkeypatch.setitem(sys.modules, "seed_demo", module)
    spec.loader.exec_module(module)
    _run(module.reset)
    yield module
    _run(module.reset)


def test_seeding_twice_adds_nothing_the_second_time(seed_demo, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["seed_demo.py"])
    assert seed_demo.main() == 0
    assert seed_demo.DEMO_PASSWORD in capsys.readouterr().out

    before = _run(_row_counts)
    again = _run(seed_demo.seed)

    assert (again.users_created, again.locations_created, again.categories_created,
            again.items_created, again.claims_created) == (0, 0, 0, 0, 0)
    assert _run(_row_counts) == before
    assert sum(again.item_status.values()) == len(seed_demo.DEMO_ITEMS)


def test_seeded_data_goes_through_the_lifecycle(seed_demo):
    from app.lifecycle import ItemStatus
    from app.repositories.item_repo import ItemRepository
    from app.repositories.user_repo import UserRepository

    report = _run(seed_demo.seed)
    assert set(report.item_status) == {s.value for s in ItemStatus}
    assert set(report.claim_status) == {"pending", "approved", "rejected"}

    def check(db):
        users, items = UserRepository(db), ItemRepository(db)
        for demo in seed_demo.DEMO_USERS:
            user = users.get_by_email(demo.email)
            assert user.email.endswith("@example.com")
            assert user.is_verified and not user.is_admin
            _, reported = items.search(reporter_id=user.id, limit=100)
            for item in reported:
                history = items.get_with_history(item.id).status_events
                # Written by the services, so every item has a full audit trail.
                assert history[0].from_status is None
                assert history[0].to_status is ItemStatus.REPORTED
                assert history[-1].to_status is item.status

    _run(check)


def test_reset_leaves_other_accounts_alone(seed_demo, client, auth_headers, monkeypatch):
    from app.core.security import hash_password
    from app.repositories.user_repo import UserRepository

    real = auth_headers()
    real_item = client.post("/items", headers=real, json={
        "name": "Real user's umbrella", "description": "Not demo data",
        "kind": "found", "occurred_on": "2026-08-01"}).json()

    # Same domain as the demo accounts, but not one of them: reset keys on the
    # exact demo list, not on "@example.com".
    bystander_email = f"bystander-{uuid.uuid4().hex[:8]}@example.com"
    _run(lambda db: UserRepository(db).create(
        email=bystander_email, password_hash=hash_password("not-a-demo-user"),
        first_name="By", last_name="Stander", roll_number="R0", batch=2026,
        course="BTECH", branch="CSE", is_verified=True,
    ))

    _run(seed_demo.seed)
    demo_item = client.get("/items", params={"q": "Purple Tupperware"}).json()["results"][0]
    claim = client.post(f"/items/{demo_item['id']}/claims", headers=real,
                        json={"evidence": "Mine, it has a steel spoon inside."})
    assert claim.status_code == 201, claim.text

    report = _run(seed_demo.reset)
    assert report.users_deleted == len(seed_demo.DEMO_USERS)
    assert report.items_deleted == len(seed_demo.DEMO_ITEMS)
    assert report.foreign_claims_deleted == 1  # the real user's claim on a demo item

    # The CLI flag reaches the same function; a second reset has nothing to do.
    monkeypatch.setattr(sys, "argv", ["seed_demo.py", "--reset"])
    assert seed_demo.main() == 0

    def remaining(db):
        users = UserRepository(db)
        assert all(users.get_by_email(d.email) is None for d in seed_demo.DEMO_USERS)
        bystander = users.get_by_email(bystander_email)
        assert bystander is not None
        users.delete(bystander)

    _run(remaining)
    assert client.get("/auth/me", headers=real).status_code == 200
    assert client.get(f"/items/{real_item['id']}").status_code == 200
    assert client.get(f"/items/{demo_item['id']}").status_code == 404
