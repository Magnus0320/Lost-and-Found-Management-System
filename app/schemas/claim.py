from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.db.models import ClaimStatus
from app.schemas.auth import PublicUserResponse
from app.schemas.common import ORMModel


class ClaimCreateRequest(BaseModel):
    evidence: str = Field(
        ..., min_length=1,
        description="How the claimant can prove the item is theirs.",
    )


class ClaimDecisionRequest(BaseModel):
    approve: bool
    note: str | None = Field(None, max_length=500)


class ClaimResponse(ORMModel):
    id: int
    item_id: int
    item_name: str | None = None
    status: ClaimStatus
    evidence: str
    created_at: datetime
    decided_at: datetime | None
    claimant: PublicUserResponse
    reporter: PublicUserResponse | None = Field(
        None,
        description=(
            "The user who reported the item. Carried here so the claimant can "
            "see who to contact without a second request."
        ),
    )


class ClaimListResponse(BaseModel):
    total: int
    results: list[ClaimResponse]


class ClaimSearchQuery(BaseModel):
    item_id: int | None = None
    status: ClaimStatus | None = None
    mine_only: bool = False
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)
