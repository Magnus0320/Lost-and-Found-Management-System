from __future__ import annotations

from sqlalchemy import func, select

from app.db.models import Category, Location
from app.repositories.base import BaseRepository


class LocationRepository(BaseRepository):
    def get(self, location_id: int) -> Location | None:
        return self.db.get(Location, location_id)

    def get_by_name(self, name: str, building: str | None) -> Location | None:
        stmt = select(Location).where(
            Location.name == name, Location.building.is_not_distinct_from(building)
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, **fields) -> Location:
        location = Location(**fields)
        self.db.add(location)
        self.db.flush()
        return location

    def list_all(self, limit: int = 100, offset: int = 0) -> tuple[int, list[Location]]:
        total = self.db.execute(select(func.count(Location.id))).scalar_one()
        stmt = select(Location).order_by(Location.name).limit(limit).offset(offset)
        return total, list(self.db.execute(stmt).scalars())


class CategoryRepository(BaseRepository):
    def get(self, category_id: int) -> Category | None:
        return self.db.get(Category, category_id)

    def get_by_name(self, name: str) -> Category | None:
        stmt = select(Category).where(Category.name == name)
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, name: str) -> Category:
        category = Category(name=name)
        self.db.add(category)
        self.db.flush()
        return category

    def list_all(self) -> tuple[int, list[Category]]:
        total = self.db.execute(select(func.count(Category.id))).scalar_one()
        stmt = select(Category).order_by(Category.name)
        return total, list(self.db.execute(stmt).scalars())
