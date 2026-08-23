from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class NotificationResponse(ORMModel):
    id: int
    item_id: int | None
    message: str
    is_read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    total: int
    results: list[NotificationResponse]
