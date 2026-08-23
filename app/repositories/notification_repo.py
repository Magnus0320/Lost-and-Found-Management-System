from __future__ import annotations

from sqlalchemy import func, select

from app.db.models import Notification
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository):
    def create(self, user_id: int, message: str, item_id: int | None = None) -> Notification:
        notification = Notification(user_id=user_id, message=message, item_id=item_id)
        self.db.add(notification)
        self.db.flush()
        return notification

    def list_for_user(
        self, user_id: int, limit: int = 50, offset: int = 0
    ) -> tuple[int, list[Notification]]:
        total = self.db.execute(
            select(func.count(Notification.id)).where(Notification.user_id == user_id)
        ).scalar_one()
        stmt = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return total, list(self.db.execute(stmt).scalars())
