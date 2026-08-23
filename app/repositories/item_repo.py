from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.db.models import Item, ItemStatusEvent
from app.lifecycle import ItemKind, ItemStatus
from app.repositories.base import BaseRepository

_EAGER = (
    selectinload(Item.category),
    selectinload(Item.location),
    selectinload(Item.reporter),
)


class ItemRepository(BaseRepository):
    def get(self, item_id: int) -> Item | None:
        stmt = select(Item).where(Item.id == item_id).options(*_EAGER)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_with_history(self, item_id: int) -> Item | None:
        stmt = (
            select(Item)
            .where(Item.id == item_id)
            .options(*_EAGER, selectinload(Item.status_events))
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def create(self, **fields) -> Item:
        item = Item(**fields)
        self.db.add(item)
        self.db.flush()
        return item

    def update(self, item: Item, **fields) -> Item:
        for key, value in fields.items():
            setattr(item, key, value)
        self.db.add(item)
        self.db.flush()
        return item

    def delete(self, item: Item) -> None:
        self.db.delete(item)
        self.db.flush()

    def set_status(self, item: Item, status: ItemStatus) -> Item:
        item.status = status
        self.db.add(item)
        self.db.flush()
        return item

    def record_status_event(
        self,
        item_id: int,
        from_status: ItemStatus | None,
        to_status: ItemStatus,
        actor_id: int | None,
        note: str | None = None,
    ) -> ItemStatusEvent:
        event = ItemStatusEvent(
            item_id=item_id,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor_id,
            note=note,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def search(
        self,
        *,
        q: str | None = None,
        category_id: int | None = None,
        location_id: int | None = None,
        status: ItemStatus | None = None,
        kind: ItemKind | None = None,
        reporter_id: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[int, list[Item]]:
        """Search the item catalogue.

        The free-text predicate is a leading-wildcard ILIKE against
        ``items.name`` and ``items.description``. Those are exactly the two
        columns carrying pg_trgm GIN indexes (``ix_items_name_trgm`` /
        ``ix_items_description_trgm``) -- a btree index would be dead weight
        for this predicate. The remaining filters are equality on indexed
        columns.
        """
        filters = []
        if q:
            pattern = f"%{q}%"
            filters.append(
                or_(Item.name.ilike(pattern), Item.description.ilike(pattern))
            )
        if category_id is not None:
            filters.append(Item.category_id == category_id)
        if location_id is not None:
            filters.append(Item.location_id == location_id)
        if status is not None:
            filters.append(Item.status == status)
        if kind is not None:
            filters.append(Item.kind == kind)
        if reporter_id is not None:
            filters.append(Item.reporter_id == reporter_id)

        count_stmt = select(func.count(Item.id))
        page_stmt = select(Item).options(*_EAGER)
        if filters:
            count_stmt = count_stmt.where(*filters)
            page_stmt = page_stmt.where(*filters)

        total = self.db.execute(count_stmt).scalar_one()
        page_stmt = (
            page_stmt.order_by(Item.occurred_on.desc(), Item.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return total, list(self.db.execute(page_stmt).scalars())
