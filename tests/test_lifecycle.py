"""Lifecycle rules -- pure unit tests, no database required."""
import pytest

from app.lifecycle import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATES,
    IllegalTransition,
    ItemStatus,
    assert_transition,
    can_transition,
)


def test_the_four_lifecycle_states_exist():
    assert [s.value for s in ItemStatus] == ["reported", "matched", "claimed", "closed"]


def test_happy_path_walks_the_whole_lifecycle():
    chain = [ItemStatus.REPORTED, ItemStatus.MATCHED, ItemStatus.CLAIMED, ItemStatus.CLOSED]
    for current, nxt in zip(chain, chain[1:]):
        assert can_transition(current, nxt), f"{current} -> {nxt} should be legal"


def test_closed_is_terminal():
    assert TERMINAL_STATES == frozenset({ItemStatus.CLOSED})
    for state in ItemStatus:
        assert not can_transition(ItemStatus.CLOSED, state)


def test_cannot_skip_from_reported_to_claimed():
    assert not can_transition(ItemStatus.REPORTED, ItemStatus.CLAIMED)


def test_any_open_state_can_be_closed():
    for state in (ItemStatus.REPORTED, ItemStatus.MATCHED, ItemStatus.CLAIMED):
        assert can_transition(state, ItemStatus.CLOSED)


def test_illegal_transition_names_both_states():
    with pytest.raises(IllegalTransition) as exc:
        assert_transition(ItemStatus.CLOSED, ItemStatus.REPORTED)
    assert "closed" in str(exc.value) and "reported" in str(exc.value)


def test_every_state_has_a_transition_rule():
    assert set(ALLOWED_TRANSITIONS) == set(ItemStatus)
