"""Request-schema validation -- no database required."""
import pytest
from pydantic import ValidationError

from app.lifecycle import ItemKind, ItemStatus
from app.schemas.auth import RegisterRequest
from app.schemas.item import ItemCreateRequest, ItemSearchQuery, StatusTransitionRequest


def test_register_rejects_a_bad_email():
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password="longenough1",
                        first_name="A", last_name="B", roll_number="R1",
                        batch=2026, course="BTECH", branch="CSE")


def test_register_rejects_a_short_password():
    with pytest.raises(ValidationError):
        RegisterRequest(email="a@b.edu", password="short", first_name="A",
                        last_name="B", roll_number="R1", batch=2026,
                        course="BTECH", branch="CSE")


def test_item_create_requires_a_known_kind():
    with pytest.raises(ValidationError):
        ItemCreateRequest(name="Bag", description="blue", kind="misplaced",
                          occurred_on="2026-08-01")


def test_item_create_accepts_a_valid_payload():
    item = ItemCreateRequest(name="Bag", description="blue", kind="lost",
                             occurred_on="2026-08-01")
    assert item.kind is ItemKind.LOST


def test_status_transition_rejects_an_unknown_state():
    with pytest.raises(ValidationError):
        StatusTransitionRequest(to_status="banana")


def test_status_transition_accepts_a_lifecycle_state():
    assert StatusTransitionRequest(to_status="closed").to_status is ItemStatus.CLOSED


def test_search_defaults_are_sane():
    q = ItemSearchQuery()
    assert q.limit == 20 and q.offset == 0 and q.q is None


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_search_limit_is_bounded(limit):
    with pytest.raises(ValidationError):
        ItemSearchQuery(limit=limit)
