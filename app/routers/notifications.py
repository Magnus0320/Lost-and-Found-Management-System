from fastapi import APIRouter, Depends

from app.db.models import User
from app.dependencies import get_current_user, get_notification_service
from app.schemas.notification import NotificationListResponse, NotificationResponse
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse, summary="Your notifications")
def list_notifications(
    service: NotificationService = Depends(get_notification_service),
    current_user: User = Depends(get_current_user),
) -> NotificationListResponse:
    total, results = service.list_for_user(current_user)
    return NotificationListResponse(
        total=total,
        results=[NotificationResponse.model_validate(n) for n in results],
    )
