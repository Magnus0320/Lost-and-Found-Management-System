from fastapi import APIRouter, Depends, status

from app.db.models import User
from app.dependencies import get_current_user, get_location_service
from app.schemas.location import (
    CategoryCreateRequest,
    CategoryListResponse,
    CategoryResponse,
    LocationCreateRequest,
    LocationListResponse,
    LocationResponse,
)
from app.services.location_service import LocationService

router = APIRouter(tags=["locations"])


@router.post(
    "/locations",
    response_model=LocationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a campus location",
)
def create_location(
    payload: LocationCreateRequest,
    service: LocationService = Depends(get_location_service),
    current_user: User = Depends(get_current_user),
) -> LocationResponse:
    return LocationResponse.model_validate(service.create_location(payload))


@router.get("/locations", response_model=LocationListResponse, summary="List locations")
def list_locations(
    service: LocationService = Depends(get_location_service),
) -> LocationListResponse:
    total, results = service.list_locations()
    return LocationListResponse(
        total=total,
        results=[LocationResponse.model_validate(loc) for loc in results],
    )


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an item category",
)
def create_category(
    payload: CategoryCreateRequest,
    service: LocationService = Depends(get_location_service),
    current_user: User = Depends(get_current_user),
) -> CategoryResponse:
    return CategoryResponse.model_validate(service.create_category(payload))


@router.get("/categories", response_model=CategoryListResponse, summary="List categories")
def list_categories(
    service: LocationService = Depends(get_location_service),
) -> CategoryListResponse:
    total, results = service.list_categories()
    return CategoryListResponse(
        total=total,
        results=[CategoryResponse.model_validate(cat) for cat in results],
    )
