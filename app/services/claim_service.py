from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.db.models import Claim, ClaimStatus, Item, User
from app.lifecycle import ItemStatus, can_transition
from app.repositories.claim_repo import ClaimRepository
from app.repositories.item_repo import ItemRepository
from app.repositories.notification_repo import NotificationRepository


class ClaimService:
    def __init__(self, db: Session) -> None:
        self.claims = ClaimRepository(db)
        self.items = ItemRepository(db)
        self.notifications = NotificationRepository(db)

    def file_claim(self, item_id: int, payload, claimant: User) -> Claim:
        item = self.items.get_for_update(item_id)
        if item is None:
            raise NotFoundError(f"No item with id {item_id}.")
        if item.status == ItemStatus.CLOSED:
            raise ConflictError("This item is closed and can no longer be claimed.")
        if item.reporter_id == claimant.id:
            raise ValidationError("You cannot claim an item you reported yourself.")
        if self.claims.get_for_item_and_user(item_id, claimant.id) is not None:
            raise ConflictError("You have already filed a claim on this item.")

        claim = self.claims.create(item_id, claimant.id, payload.evidence)

        # A claim arriving is what moves a reported item to 'matched' -- and
        # only a reported one. claimed -> matched is also a legal move, but it
        # means "withdraw the approval", which a stranger's claim must not do.
        if item.status is ItemStatus.REPORTED:
            previous = item.status
            self.items.set_status(item, ItemStatus.MATCHED)
            self.items.record_status_event(
                item_id=item.id,
                from_status=previous,
                to_status=ItemStatus.MATCHED,
                actor_id=claimant.id,
                note="Claim filed.",
            )

        self.notifications.create(
            user_id=item.reporter_id,
            item_id=item.id,
            message=f"New claim filed on '{item.name}'.",
        )
        return self.claims.get(claim.id)

    def decide(self, claim_id: int, payload, actor: User) -> Claim:
        """Approve or reject one claim, keeping the item and its other claims in step.

        * Approval is exclusive. An item may have one approved claim -- approval
          is what discloses contact details -- so approving refuses (409) while
          another approval stands, and rejects every other pending claim.
        * A rejection that leaves a `matched` item with no pending or approved
          claim sends it back to `reported`, so it is listed as unclaimed again.
        """
        claim = self.claims.get(claim_id)
        if claim is None:
            raise NotFoundError(f"No claim with id {claim_id}.")
        # Locked: a concurrent decision on the same item waits for this one.
        item = self.items.get_for_update(claim.item_id)
        if item.reporter_id != actor.id and not actor.is_admin:
            raise PermissionDeniedError(
                "Only the user who reported the item can decide its claims."
            )
        if claim.status is not ClaimStatus.PENDING:
            raise ConflictError(f"Claim already {claim.status.value}.")
        if payload.approve and self.claims.count_approved_for_item(item.id):
            raise ConflictError(
                "This item already has an approved claim. Move the item back to "
                "'matched' to withdraw that approval before approving another."
            )

        self.claims.decide(claim, payload.approve, actor.id)
        if payload.approve:
            self._approve(item, claim, payload, actor)
        else:
            self._after_rejection(item, payload, actor)

        self.notifications.create(
            user_id=claim.claimant_id,
            item_id=item.id,
            message=(
                f"Your claim on '{item.name}' was "
                f"{'approved' if payload.approve else 'rejected'}."
            ),
        )
        return self.claims.get(claim_id)

    def _approve(self, item: Item, claim: Claim, payload, actor: User) -> None:
        superseded = self.claims.reject_pending_for_item(
            item.id, superseded_by=claim, decided_by_id=actor.id
        )
        if can_transition(item.status, ItemStatus.CLAIMED):
            previous = item.status
            self.items.set_status(item, ItemStatus.CLAIMED)
            self.items.record_status_event(
                item_id=item.id,
                from_status=previous,
                to_status=ItemStatus.CLAIMED,
                actor_id=actor.id,
                note=payload.note or "Claim approved.",
            )
        for other in superseded:
            self.notifications.create(
                user_id=other.claimant_id,
                item_id=item.id,
                message=(
                    f"Your claim on '{item.name}' was rejected: another claim "
                    "was approved."
                ),
            )

    def _after_rejection(self, item: Item, payload, actor: User) -> None:
        if item.status is not ItemStatus.MATCHED:
            return
        if self.claims.count_open_for_item(item.id):
            return  # other claims are still waiting for a decision
        self.items.set_status(item, ItemStatus.REPORTED)
        self.items.record_status_event(
            item_id=item.id,
            from_status=ItemStatus.MATCHED,
            to_status=ItemStatus.REPORTED,
            actor_id=actor.id,
            note="All claims rejected." + (f" {payload.note}" if payload.note else ""),
        )

    def contact_disclosed_to(self, claim: Claim, viewer: User | None) -> bool:
        """May `viewer` see the other party's contact details on this claim?

        Only once the claim is approved, and only to the two people it is
        actually between. Reopening the claim takes the disclosure away with
        it, since the condition is re-evaluated on every read.
        """
        if viewer is None or claim.status is not ClaimStatus.APPROVED:
            return False
        if viewer.is_admin:
            return True
        return viewer.id in (claim.claimant_id, claim.item.reporter_id)

    def search(self, query, actor: User) -> tuple[int, list[Claim]]:
        """Claims the actor is a party to.

        A claim is between the person who filed it and the reporter of the item
        it is against; those two can read it and nobody else. Without that
        scope, `?item_id=` on a stranger's item would hand back the evidence
        field, which is where people are told to put serial numbers and
        receipts. `mine_only` narrows further, to claims the actor filed.

        Admins are the exception on both counts: the oversight role is
        pointless if it cannot see what it is meant to oversee.
        """
        return self.claims.search(
            item_id=query.item_id,
            status=query.status,
            claimant_id=actor.id if query.mine_only else None,
            visible_to_id=None if actor.is_admin else actor.id,
            limit=query.limit,
            offset=query.offset,
        )
