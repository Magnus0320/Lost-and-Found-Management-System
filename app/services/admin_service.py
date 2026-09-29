from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.db.models import User
from app.repositories.claim_repo import ClaimRepository
from app.repositories.item_repo import ItemRepository
from app.repositories.location_repo import CategoryRepository, LocationRepository
from app.repositories.user_repo import UserRepository


class AdminService:
    """Staff operations.

    Every method here assumes the caller has already been checked by
    ``get_admin_user``; this layer enforces the rules that hold even *for* an
    admin -- chiefly that they cannot lock themselves out or quietly remove a
    colleague's oversight.
    """

    def __init__(self, db: Session) -> None:
        self.users = UserRepository(db)
        self.items = ItemRepository(db)
        self.claims = ClaimRepository(db)
        self.locations = LocationRepository(db)
        self.categories = CategoryRepository(db)

    def stats(self) -> dict[str, int]:
        return {
            "items": self.items.count(),
            "users": self.users.count(),
            "claims": self.claims.count(),
            "admins": self.users.count(admins_only=True),
        }

    def list_users(self, query) -> tuple[int, list[User]]:
        return self.users.search(q=query.q, limit=query.limit, offset=query.offset)

    def set_role(self, user_id: int, is_admin: bool, actor: User) -> User:
        user = self.users.get(user_id)
        if user is None:
            raise NotFoundError(f"No user with id {user_id}.")
        if user.id == actor.id and not is_admin:
            raise ValidationError(
                "You cannot remove your own administrator access. Ask another "
                "admin to do it, so the system is never left without one."
            )
        return self.users.set_admin(user, is_admin)

    def delete_user(self, user_id: int, actor: User) -> None:
        user = self.users.get(user_id)
        if user is None:
            raise NotFoundError(f"No user with id {user_id}.")
        if user.id == actor.id:
            raise ValidationError("You cannot delete your own account here.")
        if user.is_admin:
            raise ValidationError(
                "Remove this user's administrator access first. Deleting an "
                "admin outright is too easy to do by mistake."
            )
        self.users.delete(user)

    def bulk_delete_items(self, item_ids: list[int]) -> tuple[int, int]:
        """Returns (requested, actually deleted). Ids that no longer exist are
        not an error -- the end state the caller asked for is the same."""
        unique = list(dict.fromkeys(item_ids))
        return len(unique), self.items.delete_many(unique)

    def delete_location(self, location_id: int) -> None:
        location = self.locations.get(location_id)
        if location is None:
            raise NotFoundError(f"No location with id {location_id}.")
        self.locations.delete(location)

    def delete_category(self, category_id: int) -> None:
        category = self.categories.get(category_id)
        if category is None:
            raise NotFoundError(f"No category with id {category_id}.")
        self.categories.delete(category)
