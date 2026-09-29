from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.auth import UserResponse


class AdminStatsResponse(BaseModel):
    """Row counts for the admin dashboard."""

    items: int
    users: int
    claims: int
    admins: int


class UserListResponse(BaseModel):
    total: int
    results: list[UserResponse]


class UserSearchQuery(BaseModel):
    q: str | None = Field(
        None, min_length=1, max_length=120,
        description="Match against email, name or roll number.",
    )
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class RoleUpdateRequest(BaseModel):
    is_admin: bool


class BulkDeleteRequest(BaseModel):
    """Ids to delete. Capped so one request cannot wipe the table by accident."""

    item_ids: list[int] = Field(..., min_length=1, max_length=500)


class BulkDeleteResponse(BaseModel):
    requested: int
    deleted: int
    detail: str
