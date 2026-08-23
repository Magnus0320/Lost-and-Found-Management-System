from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.db.models import Category, Location
from app.repositories.location_repo import CategoryRepository, LocationRepository


class LocationService:
    def __init__(self, db: Session) -> None:
        self.locations = LocationRepository(db)
        self.categories = CategoryRepository(db)

    def create_location(self, payload) -> Location:
        existing = self.locations.get_by_name(payload.name, payload.building)
        if existing is not None:
            raise ConflictError("That location already exists.")
        return self.locations.create(
            name=payload.name,
            building=payload.building,
            description=payload.description,
        )

    def list_locations(self, limit: int = 100, offset: int = 0):
        return self.locations.list_all(limit=limit, offset=offset)

    def create_category(self, payload) -> Category:
        if self.categories.get_by_name(payload.name) is not None:
            raise ConflictError("That category already exists.")
        return self.categories.create(payload.name)

    def list_categories(self):
        return self.categories.list_all()
