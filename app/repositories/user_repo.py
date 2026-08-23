from __future__ import annotations

from sqlalchemy import select

from app.db.models import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    def get(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower())
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, **fields) -> User:
        user = User(**fields)
        self.db.add(user)
        self.db.flush()
        return user

    def mark_verified(self, user: User) -> User:
        user.is_verified = True
        self.db.add(user)
        self.db.flush()
        return user

    def set_password_hash(self, user: User, password_hash: str) -> User:
        user.password_hash = password_hash
        self.db.add(user)
        self.db.flush()
        return user
