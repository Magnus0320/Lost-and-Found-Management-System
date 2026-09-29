from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError
from app.db.models import Claim, ClaimStatus, Item
from app.repositories.base import BaseRepository

# The reporter of the item travels with every claim: both sides of an approved
# claim are shown to each other, so serialising one needs both users loaded.
_EAGER = (
    selectinload(Claim.claimant),
    selectinload(Claim.item).selectinload(Item.reporter),
)


class ClaimRepository(BaseRepository):
    def get(self, claim_id: int) -> Claim | None:
        stmt = select(Claim).where(Claim.id == claim_id).options(*_EAGER)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_for_item_and_user(self, item_id: int, user_id: int) -> Claim | None:
        stmt = select(Claim).where(
            Claim.item_id == item_id, Claim.claimant_id == user_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, item_id: int, claimant_id: int, evidence: str) -> Claim:
        claim = Claim(item_id=item_id, claimant_id=claimant_id, evidence=evidence)
        self.db.add(claim)
        self.db.flush()
        return claim

    def decide(
        self, claim: Claim, approved: bool, decided_by_id: int
    ) -> Claim:
        claim.status = ClaimStatus.APPROVED if approved else ClaimStatus.REJECTED
        claim.decided_at = datetime.now(tz=timezone.utc)
        claim.decided_by_id = decided_by_id
        self.db.add(claim)
        try:
            self.db.flush()
        except IntegrityError as exc:
            # uq_claims_one_approved_per_item: the service checks first, so this
            # is only reachable by a concurrent approval that got there first.
            raise ConflictError("This item already has an approved claim.") from exc
        return claim

    def reject_pending_for_item(
        self, item_id: int, superseded_by: Claim, decided_by_id: int
    ) -> list[Claim]:
        """Reject every other pending claim on an item, recording which claim
        won. Returns the claims it rejected."""
        stmt = (
            select(Claim)
            .where(
                Claim.item_id == item_id,
                Claim.status == ClaimStatus.PENDING,
                Claim.id != superseded_by.id,
            )
            .options(*_EAGER)
        )
        claims = list(self.db.execute(stmt).scalars())
        now = datetime.now(tz=timezone.utc)
        for claim in claims:
            claim.status = ClaimStatus.REJECTED
            claim.decided_at = now
            claim.decided_by_id = decided_by_id
            claim.superseded_by_id = superseded_by.id
            self.db.add(claim)
        if claims:
            self.db.flush()
        return claims

    def search(
        self,
        *,
        item_id: int | None = None,
        status: ClaimStatus | None = None,
        claimant_id: int | None = None,
        visible_to_id: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[int, list[Claim]]:
        filters = []
        if item_id is not None:
            filters.append(Claim.item_id == item_id)
        if status is not None:
            filters.append(Claim.status == status)
        if claimant_id is not None:
            filters.append(Claim.claimant_id == claimant_id)
        if visible_to_id is not None:
            # A claim is between two people: whoever filed it, and whoever
            # reported the item it is against. Nobody else can read it -- the
            # evidence field holds serial numbers and receipts.
            filters.append(
                or_(
                    Claim.claimant_id == visible_to_id,
                    Claim.item_id.in_(
                        select(Item.id).where(Item.reporter_id == visible_to_id)
                    ),
                )
            )

        count_stmt = select(func.count(Claim.id))
        page_stmt = select(Claim).options(*_EAGER)
        if filters:
            count_stmt = count_stmt.where(*filters)
            page_stmt = page_stmt.where(*filters)

        total = self.db.execute(count_stmt).scalar_one()
        page_stmt = page_stmt.order_by(Claim.created_at.desc()).limit(limit).offset(offset)
        return total, list(self.db.execute(page_stmt).scalars())

    def reopen_approved_for_item(self, item_id: int) -> list[Claim]:
        """Send every approved claim on an item back to `pending`.

        Called when the item is moved back out of `claimed`: the approval is
        what put it there, so undoing the one has to undo the other, or the
        item and its claim end up describing different realities.
        """
        stmt = (
            select(Claim)
            .where(Claim.item_id == item_id, Claim.status == ClaimStatus.APPROVED)
            .options(*_EAGER)
        )
        claims = list(self.db.execute(stmt).scalars())
        for claim in claims:
            claim.status = ClaimStatus.PENDING
            claim.decided_at = None
            claim.decided_by_id = None
            self.db.add(claim)
        if claims:
            self.db.flush()
        return claims

    def reopen_superseded_by(self, claim_ids: list[int]) -> list[Claim]:
        """Send claims that were auto-rejected in favour of `claim_ids` back to
        `pending` -- the approval that beat them has been withdrawn."""
        if not claim_ids:
            return []
        stmt = (
            select(Claim)
            .where(
                Claim.superseded_by_id.in_(claim_ids),
                Claim.status == ClaimStatus.REJECTED,
            )
            .options(*_EAGER)
        )
        claims = list(self.db.execute(stmt).scalars())
        for claim in claims:
            claim.status = ClaimStatus.PENDING
            claim.decided_at = None
            claim.decided_by_id = None
            claim.superseded_by_id = None
            self.db.add(claim)
        if claims:
            self.db.flush()
        return claims

    def count_open_for_item(self, item_id: int) -> int:
        """Claims on an item still pending or approved -- i.e. not rejected."""
        stmt = select(func.count(Claim.id)).where(
            Claim.item_id == item_id,
            Claim.status.in_((ClaimStatus.PENDING, ClaimStatus.APPROVED)),
        )
        return self.db.execute(stmt).scalar_one()

    def count_approved_for_item(self, item_id: int) -> int:
        stmt = select(func.count(Claim.id)).where(
            Claim.item_id == item_id, Claim.status == ClaimStatus.APPROVED
        )
        return self.db.execute(stmt).scalar_one()

    def count(self) -> int:
        return self.db.execute(select(func.count(Claim.id))).scalar_one()
