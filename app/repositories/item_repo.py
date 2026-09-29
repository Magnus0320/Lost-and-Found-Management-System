from __future__ import annotations

from datetime import date

from sqlalchemy import delete as sa_delete
from sqlalchemy import Float, case, func, literal, or_, select
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

    def get_for_update(self, item_id: int) -> Item | None:
        """Fetch an item and lock its row until the transaction ends.

        Claim decisions and filings take this lock, so two of them on the same
        item run one after the other and each sees the other's outcome.
        """
        stmt = select(Item).where(Item.id == item_id).options(*_EAGER).with_for_update()
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

    def suggest_matches(
        self,
        source: Item,
        *,
        kind: ItemKind,
        name_weight: float,
        min_similarity: float,
        category_boost: float,
        location_boost: float,
        date_boost: float,
        date_from: date,
        date_to: date,
        limit: int,
    ) -> list[tuple[Item, float, float, bool, bool, bool]]:
        """Open items of `kind` that read like `source`, best first.

        Text similarity is pg_trgm ``similarity()``: a weighted blend of
        name-vs-name and (name + description)-vs-(name + description). Rows below
        `min_similarity` are dropped *before* the boosts are added, so sharing a
        category or a location can never turn an unrelated item into a match.

        This scores every open item of the opposite kind -- a filter on a
        computed score cannot use the trigram GIN indexes. Returns
        ``(item, score, similarity, same_category, same_location, close_date)``.
        """
        source_text = f"{source.name} {source.description}"
        similarity = (
            name_weight * func.similarity(Item.name, source.name)
            + (1 - name_weight)
            * func.similarity(Item.name + " " + Item.description, source_text)
        ).label("similarity")

        def flag(condition):
            return condition if condition is not None else literal(False)

        same_category = flag(
            Item.category_id == source.category_id if source.category_id else None
        )
        same_location = flag(
            Item.location_id == source.location_id if source.location_id else None
        )
        close_date = Item.occurred_on.between(date_from, date_to)

        def boost(condition, amount: float):
            return case((condition, literal(amount, Float)), else_=literal(0.0, Float))

        scored = (
            select(
                Item.id.label("id"),
                similarity,
                same_category.label("same_category"),
                same_location.label("same_location"),
                close_date.label("close_date"),
            )
            .where(
                Item.kind == kind,
                Item.status != ItemStatus.CLOSED,
                Item.reporter_id != source.reporter_id,
                Item.id != source.id,
            )
            .subquery()
        )
        score = (
            scored.c.similarity
            + boost(scored.c.same_category, category_boost)
            + boost(scored.c.same_location, location_boost)
            + boost(scored.c.close_date, date_boost)
        ).label("score")
        stmt = (
            select(
                Item, score, scored.c.similarity, scored.c.same_category,
                scored.c.same_location, scored.c.close_date,
            )
            .join(scored, Item.id == scored.c.id)
            .where(scored.c.similarity >= min_similarity)
            .options(*_EAGER)
            .order_by(score.desc(), scored.c.similarity.desc(), Item.id.desc())
            .limit(limit)
        )
        return [tuple(row) for row in self.db.execute(stmt).all()]

    def delete_many(self, item_ids: list[int]) -> int:
        """Delete items by id in one statement; returns how many went.

        Cascades to each item's claims and status events, so the audit trail
        of a deleted item goes with it rather than being orphaned.
        """
        if not item_ids:
            return 0
        result = self.db.execute(sa_delete(Item).where(Item.id.in_(item_ids)))
        self.db.flush()
        return int(result.rowcount or 0)

    def count(self) -> int:
        return self.db.execute(select(func.count(Item.id))).scalar_one()
