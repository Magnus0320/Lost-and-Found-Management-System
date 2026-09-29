from __future__ import annotations

from sqlalchemy import func, or_, select

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

    def search(
        self, *, q: str | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[int, list[User]]:
        """Every account, newest first. Admin-only -- see app/routers/admin.py."""
        filters = []
        if q:
            like = f"%{q}%"
            filters.append(
                or_(
                    User.email.ilike(like),
                    User.first_name.ilike(like),
                    User.last_name.ilike(like),
                    User.roll_number.ilike(like),
                )
            )
        count_stmt = select(func.count(User.id))
        page_stmt = select(User)
        if filters:
            count_stmt = count_stmt.where(*filters)
            page_stmt = page_stmt.where(*filters)
        total = self.db.execute(count_stmt).scalar_one()
        page_stmt = page_stmt.order_by(User.id.desc()).limit(limit).offset(offset)
        return total, list(self.db.execute(page_stmt).scalars())

    def set_admin(self, user: User, is_admin: bool) -> User:
        user.is_admin = is_admin
        self.db.add(user)
        self.db.flush()
        return user

    def delete(self, user: User) -> None:
        """Removes the account and, by ON DELETE CASCADE, its items and claims."""
        self.db.delete(user)
        self.db.flush()

    def list_admins(self) -> list[User]:
        stmt = select(User).where(User.is_admin.is_(True)).order_by(User.id)
        return list(self.db.execute(stmt).scalars())

    def count(self, *, admins_only: bool = False) -> int:
        stmt = select(func.count(User.id))
        if admins_only:
            stmt = stmt.where(User.is_admin.is_(True))
        return self.db.execute(stmt).scalar_one()
