from fastapi import APIRouter, Depends

from app.dependencies import get_location_service
from app.schemas.common import HealthResponse
from app.services.location_service import LocationService

router = APIRouter(tags=["health"])

API_VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse, summary="Liveness / DB reachability")
def health(service: LocationService = Depends(get_location_service)) -> HealthResponse:
    try:
        service.list_categories()
        database = "reachable"
    except Exception:  # pragma: no cover - reported, not raised
        database = "unreachable"
    return HealthResponse(status="ok", database=database, version=API_VERSION)
