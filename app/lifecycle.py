"""Item lifecycle: the states an item moves through and the legal moves.

reported -> matched -> claimed -> closed

Kept deliberately free of any framework or ORM import so the transition rules
can be unit-tested (and reasoned about) on their own.
"""
from __future__ import annotations

import enum


class ItemStatus(str, enum.Enum):
    """Lifecycle state of a reported item."""

    REPORTED = "reported"
    MATCHED = "matched"
    CLAIMED = "claimed"
    CLOSED = "closed"


class ItemKind(str, enum.Enum):
    """Whether the item was lost by someone or found by someone.

    Orthogonal to lifecycle state: a `found` item and a `lost` item both travel
    reported -> matched -> claimed -> closed.
    """

    LOST = "lost"
    FOUND = "found"


#: Legal forward and corrective transitions. `closed` is terminal.
ALLOWED_TRANSITIONS: dict[ItemStatus, frozenset[ItemStatus]] = {
    ItemStatus.REPORTED: frozenset({ItemStatus.MATCHED, ItemStatus.CLOSED}),
    ItemStatus.MATCHED: frozenset(
        {ItemStatus.CLAIMED, ItemStatus.REPORTED, ItemStatus.CLOSED}
    ),
    ItemStatus.CLAIMED: frozenset({ItemStatus.CLOSED, ItemStatus.MATCHED}),
    ItemStatus.CLOSED: frozenset(),
}

TERMINAL_STATES: frozenset[ItemStatus] = frozenset(
    state for state, nxt in ALLOWED_TRANSITIONS.items() if not nxt
)


class IllegalTransition(ValueError):
    """Raised when a caller asks for a move the lifecycle does not allow."""

    def __init__(self, current: ItemStatus, requested: ItemStatus) -> None:
        self.current = current
        self.requested = requested
        allowed = sorted(s.value for s in ALLOWED_TRANSITIONS[current])
        detail = ", ".join(allowed) if allowed else "nothing (terminal state)"
        super().__init__(
            f"Cannot move item from '{current.value}' to '{requested.value}'. "
            f"Allowed from '{current.value}': {detail}."
        )


def can_transition(current: ItemStatus, requested: ItemStatus) -> bool:
    return requested in ALLOWED_TRANSITIONS[current]


def assert_transition(current: ItemStatus, requested: ItemStatus) -> None:
    """Raise :class:`IllegalTransition` unless the move is legal."""
    if not can_transition(current, requested):
        raise IllegalTransition(current, requested)
