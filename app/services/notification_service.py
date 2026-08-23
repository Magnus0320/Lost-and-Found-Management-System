from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import User
from app.repositories.notification_repo import NotificationRepository


class NotificationService:
    def __init__(self, db: Session) -> None:
        self.notifications = NotificationRepository(db)

    def list_for_user(self, user: User, limit: int = 50, offset: int = 0):
        return self.notifications.list_for_user(user.id, limit=limit, offset=offset)
