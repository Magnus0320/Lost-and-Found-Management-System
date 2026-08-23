from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.lifecycle import ItemKind, ItemStatus
from app.schemas.auth import UserResponse
from app.schemas.common import ORMModel
from app.schemas.location import CategoryResponse, LocationResponse


class ItemCreateRequest(BaseModel):
    """Body for registering a newly lost/found item."""

    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(..., min_length=1)
    kind: ItemKind
    occurred_on: date
    category_id: int | None = None
    location_id: int | None = None
    image_path: str | None = Field(None, max_length=255)


class ItemUpdateRequest(BaseModel):
    """Partial update. Lifecycle state is deliberately NOT settable here --
    it moves only through the status-transition endpoint."""

    name: str | None = Field(None, min_length=1, max_length=120)
    description: str | None = Field(None, min_length=1)
    kind: ItemKind | None = None
    occurred_on: date | None = None
    category_id: int | None = None
    location_id: int | None = None
    image_path: str | None = Field(None, max_length=255)


class StatusTransitionRequest(BaseModel):
    """Body for moving an item along reported -> matched -> claimed -> closed."""

    to_status: ItemStatus
    note: str | None = Field(None, max_length=500)


class ItemSearchQuery(BaseModel):
    """Typed query-string model for the search endpoint.

    Used via ``Depends`` so GET input is Pydantic-validated too, not just bodies.
    """

    q: str | None = Field(
        None, min_length=1, max_length=120,
        description="Free-text match against item name and description.",
    )
    category_id: int | None = None
    location_id: int | None = None
    status: ItemStatus | None = None
    kind: ItemKind | None = None
    reporter_id: int | None = None
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class StatusEventResponse(ORMModel):
    id: int
    from_status: ItemStatus | None
    to_status: ItemStatus
    note: str | None
    created_at: datetime


class ItemResponse(ORMModel):
    id: int
    name: str
    description: str
    kind: ItemKind
    status: ItemStatus
    occurred_on: date
    image_path: str | None
    created_at: datetime
    updated_at: datetime
    category: CategoryResponse | None
    location: LocationResponse | None
    reporter: UserResponse


class ItemDetailResponse(ItemResponse):
    status_events: list[StatusEventResponse] = []


class ItemListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    results: list[ItemResponse]
