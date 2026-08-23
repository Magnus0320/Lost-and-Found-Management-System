from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.models import Claim, ClaimStatus
from app.repositories.base import BaseRepository

_EAGER = (selectinload(Claim.claimant),)


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
        self.db.flush()
        return claim

    def search(
        self,
        *,
        item_id: int | None = None,
        status: ClaimStatus | None = None,
        claimant_id: int | None = None,
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

        count_stmt = select(func.count(Claim.id))
        page_stmt = select(Claim).options(*_EAGER)
        if filters:
            count_stmt = count_stmt.where(*filters)
            page_stmt = page_stmt.where(*filters)

        total = self.db.execute(count_stmt).scalar_one()
        page_stmt = page_stmt.order_by(Claim.created_at.desc()).limit(limit).offset(offset)
        return total, list(self.db.execute(page_stmt).scalars())

    def count_approved_for_item(self, item_id: int) -> int:
        stmt = select(func.count(Claim.id)).where(
            Claim.item_id == item_id, Claim.status == ClaimStatus.APPROVED
        )
        return self.db.execute(stmt).scalar_one()
