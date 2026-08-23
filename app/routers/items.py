from fastapi import APIRouter, Depends, Path, status

from app.db.models import User
from app.dependencies import get_current_user, get_item_service
from app.schemas.common import MessageResponse
from app.schemas.item import (
    ItemCreateRequest,
    ItemDetailResponse,
    ItemListResponse,
    ItemResponse,
    ItemSearchQuery,
    ItemUpdateRequest,
    StatusTransitionRequest,
)
from app.services.item_service import ItemService

router = APIRouter(prefix="/items", tags=["items"])


@router.post(
    "",
    response_model=ItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a lost or found item",
)
def register_item(
    payload: ItemCreateRequest,
    service: ItemService = Depends(get_item_service),
    current_user: User = Depends(get_current_user),
) -> ItemResponse:
    item = service.register_item(payload, current_user)
    return ItemResponse.model_validate(item)


@router.get(
    "",
    response_model=ItemListResponse,
    summary="Search items by text, category, location, kind and lifecycle state",
)
def search_items(
    query: ItemSearchQuery = Depends(),
    service: ItemService = Depends(get_item_service),
) -> ItemListResponse:
    total, results = service.search(query)
    return ItemListResponse(
        total=total,
        limit=query.limit,
        offset=query.offset,
        results=[ItemResponse.model_validate(item) for item in results],
    )


@router.get(
    "/{item_id}",
    response_model=ItemDetailResponse,
    summary="Fetch one item with its lifecycle history",
)
def get_item(
    item_id: int = Path(..., ge=1),
    service: ItemService = Depends(get_item_service),
) -> ItemDetailResponse:
    item = service.get_detail(item_id)
    return ItemDetailResponse.model_validate(item)


@router.patch(
    "/{item_id}",
    response_model=ItemResponse,
    summary="Edit an item's descriptive fields",
)
def update_item(
    payload: ItemUpdateRequest,
    item_id: int = Path(..., ge=1),
    service: ItemService = Depends(get_item_service),
    current_user: User = Depends(get_current_user),
) -> ItemResponse:
    item = service.update(item_id, payload, current_user)
    return ItemResponse.model_validate(item)


@router.post(
    "/{item_id}/status",
    response_model=ItemDetailResponse,
    summary="Move an item along reported -> matched -> claimed -> closed",
)
def transition_status(
    payload: StatusTransitionRequest,
    item_id: int = Path(..., ge=1),
    service: ItemService = Depends(get_item_service),
    current_user: User = Depends(get_current_user),
) -> ItemDetailResponse:
    service.transition_status(item_id, payload, current_user)
    return ItemDetailResponse.model_validate(service.get_detail(item_id))


@router.delete(
    "/{item_id}",
    response_model=MessageResponse,
    summary="Delete an item you reported",
)
def delete_item(
    item_id: int = Path(..., ge=1),
    service: ItemService = Depends(get_item_service),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    service.delete(item_id, current_user)
    return MessageResponse(detail=f"Item {item_id} deleted.")
