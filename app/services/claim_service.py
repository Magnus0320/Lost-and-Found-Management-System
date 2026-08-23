from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.db.models import Claim, ClaimStatus, User
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
        item = self.items.get(item_id)
        if item is None:
            raise NotFoundError(f"No item with id {item_id}.")
        if item.status == ItemStatus.CLOSED:
            raise ConflictError("This item is closed and can no longer be claimed.")
        if item.reporter_id == claimant.id:
            raise ValidationError("You cannot claim an item you reported yourself.")
        if self.claims.get_for_item_and_user(item_id, claimant.id) is not None:
            raise ConflictError("You have already filed a claim on this item.")

        claim = self.claims.create(item_id, claimant.id, payload.evidence)

        # A claim arriving is what moves a reported item to 'matched'.
        if can_transition(item.status, ItemStatus.MATCHED):
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
        claim = self.claims.get(claim_id)
        if claim is None:
            raise NotFoundError(f"No claim with id {claim_id}.")
        item = self.items.get(claim.item_id)
        if item.reporter_id != actor.id:
            raise PermissionDeniedError(
                "Only the user who reported the item can decide its claims."
            )
        if claim.status is not ClaimStatus.PENDING:
            raise ConflictError(f"Claim already {claim.status.value}.")

        self.claims.decide(claim, payload.approve, actor.id)

        if payload.approve and can_transition(item.status, ItemStatus.CLAIMED):
            previous = item.status
            self.items.set_status(item, ItemStatus.CLAIMED)
            self.items.record_status_event(
                item_id=item.id,
                from_status=previous,
                to_status=ItemStatus.CLAIMED,
                actor_id=actor.id,
                note=payload.note or "Claim approved.",
            )

        self.notifications.create(
            user_id=claim.claimant_id,
            item_id=item.id,
            message=(
                f"Your claim on '{item.name}' was "
                f"{'approved' if payload.approve else 'rejected'}."
            ),
        )
        return self.claims.get(claim_id)

    def search(self, query, actor: User) -> tuple[int, list[Claim]]:
        return self.claims.search(
            item_id=query.item_id,
            status=query.status,
            claimant_id=actor.id if query.mine_only else None,
            limit=query.limit,
            offset=query.offset,
        )
