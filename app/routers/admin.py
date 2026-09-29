"""Staff routes.

Every route here depends on ``get_admin_user``, so a non-admin token gets 403
before any handler body runs. The oversight this role provides is the answer
to an obvious hole in the lifecycle: a reporter decides the claims on their own
item, and without staff there is nobody to correct a wrong decision.
"""
from fastapi import APIRouter, Depends, Path

from app.db.models import User
from app.dependencies import (
    get_admin_user,
    get_admin_service,
    get_item_service,
)
from app.schemas.admin import (
    AdminStatsResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    RoleUpdateRequest,
    UserListResponse,
    UserSearchQuery,
)
from app.schemas.auth import UserResponse
from app.schemas.common import MessageResponse
from app.services.admin_service import AdminService
from app.services.item_service import ItemService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStatsResponse, summary="Row counts")
def stats(
    service: AdminService = Depends(get_admin_service),
    _: User = Depends(get_admin_user),
) -> AdminStatsResponse:
    return AdminStatsResponse(**service.stats())


@router.get("/users", response_model=UserListResponse, summary="List every account")
def list_users(
    query: UserSearchQuery = Depends(),
    service: AdminService = Depends(get_admin_service),
    _: User = Depends(get_admin_user),
) -> UserListResponse:
    total, results = service.list_users(query)
    return UserListResponse(
        total=total,
        results=[UserResponse.model_validate(u) for u in results],
    )


@router.post(
    "/users/{user_id}/role",
    response_model=UserResponse,
    summary="Grant or revoke administrator access",
)
def set_role(
    payload: RoleUpdateRequest,
    user_id: int = Path(..., ge=1),
    service: AdminService = Depends(get_admin_service),
    admin: User = Depends(get_admin_user),
) -> UserResponse:
    return UserResponse.model_validate(
        service.set_role(user_id, payload.is_admin, admin)
    )


@router.delete(
    "/users/{user_id}",
    response_model=MessageResponse,
    summary="Delete an account and everything it reported",
)
def delete_user(
    user_id: int = Path(..., ge=1),
    service: AdminService = Depends(get_admin_service),
    admin: User = Depends(get_admin_user),
) -> MessageResponse:
    service.delete_user(user_id, admin)
    return MessageResponse(detail=f"User {user_id} deleted.")


@router.post(
    "/items/bulk-delete",
    response_model=BulkDeleteResponse,
    summary="Delete many items at once",
)
def bulk_delete_items(
    payload: BulkDeleteRequest,
    service: AdminService = Depends(get_admin_service),
    _: User = Depends(get_admin_user),
) -> BulkDeleteResponse:
    requested, deleted = service.bulk_delete_items(payload.item_ids)
    return BulkDeleteResponse(
        requested=requested,
        deleted=deleted,
        detail=f"Deleted {deleted} of {requested} item(s).",
    )


@router.delete(
    "/locations/{location_id}",
    response_model=MessageResponse,
    summary="Delete a campus location",
)
def delete_location(
    location_id: int = Path(..., ge=1),
    service: AdminService = Depends(get_admin_service),
    _: User = Depends(get_admin_user),
) -> MessageResponse:
    service.delete_location(location_id)
    return MessageResponse(detail=f"Location {location_id} deleted.")


@router.delete(
    "/categories/{category_id}",
    response_model=MessageResponse,
    summary="Delete an item category",
)
def delete_category(
    category_id: int = Path(..., ge=1),
    service: AdminService = Depends(get_admin_service),
    _: User = Depends(get_admin_user),
) -> MessageResponse:
    service.delete_category(category_id)
    return MessageResponse(detail=f"Category {category_id} deleted.")


@router.delete(
    "/items/{item_id}",
    response_model=MessageResponse,
    summary="Delete any item, whoever reported it",
)
def delete_item(
    item_id: int = Path(..., ge=1),
    items: ItemService = Depends(get_item_service),
    admin: User = Depends(get_admin_user),
) -> MessageResponse:
    # ItemService already lets an admin past the reporter check.
    items.delete(item_id, admin)
    return MessageResponse(detail=f"Item {item_id} deleted.")
