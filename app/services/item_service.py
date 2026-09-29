from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from app.db.models import ClaimStatus, Item, User
from app.lifecycle import ItemStatus, IllegalTransition, assert_transition
from app.repositories.claim_repo import ClaimRepository
from app.repositories.item_repo import ItemRepository
from app.repositories.location_repo import CategoryRepository, LocationRepository
from app.repositories.notification_repo import NotificationRepository


class ItemService:
    def __init__(self, db: Session) -> None:
        self.items = ItemRepository(db)
        self.claims = ClaimRepository(db)
        self.locations = LocationRepository(db)
        self.categories = CategoryRepository(db)
        self.notifications = NotificationRepository(db)

    def register_item(self, payload, reporter: User) -> Item:
        self._validate_refs(payload.category_id, payload.location_id)
        item = self.items.create(
            name=payload.name,
            description=payload.description,
            kind=payload.kind,
            status=ItemStatus.REPORTED,
            occurred_on=payload.occurred_on,
            category_id=payload.category_id,
            location_id=payload.location_id,
            image_path=payload.image_path,
            reporter_id=reporter.id,
        )
        self.items.record_status_event(
            item_id=item.id,
            from_status=None,
            to_status=ItemStatus.REPORTED,
            actor_id=reporter.id,
            note="Item reported.",
        )
        return self.items.get(item.id)

    def search(self, query) -> tuple[int, list[Item]]:
        return self.items.search(
            q=query.q,
            category_id=query.category_id,
            location_id=query.location_id,
            status=query.status,
            kind=query.kind,
            reporter_id=query.reporter_id,
            limit=query.limit,
            offset=query.offset,
        )

    def get(self, item_id: int) -> Item:
        item = self.items.get(item_id)
        if item is None:
            raise NotFoundError(f"No item with id {item_id}.")
        return item

    def get_detail(self, item_id: int) -> Item:
        item = self.items.get_with_history(item_id)
        if item is None:
            raise NotFoundError(f"No item with id {item_id}.")
        return item

    def update(self, item_id: int, payload, actor: User) -> Item:
        item = self.get(item_id)
        self._require_reporter(item, actor)
        fields = payload.model_dump(exclude_unset=True)
        if not fields:
            raise ValidationError("No fields supplied to update.")
        self._validate_refs(fields.get("category_id"), fields.get("location_id"))
        self.items.update(item, **fields)
        return self.items.get(item_id)

    def transition_status(self, item_id: int, payload, actor: User) -> Item:
        """Move an item along reported -> matched -> claimed -> closed."""
        item = self.get(item_id)
        self._require_reporter(item, actor)
        current = item.status
        try:
            assert_transition(current, payload.to_status)
        except IllegalTransition as exc:
            raise ValidationError(str(exc)) from exc

        # Moving back out of `claimed` withdraws the approval that put the item
        # there. The claim has to follow, otherwise the item reads "awaiting a
        # decision" while carrying a claim that is already decided and, because
        # decisions are one-shot, can never be decided again.
        reopened = []
        if current is ItemStatus.CLAIMED and payload.to_status is not ItemStatus.CLOSED:
            reopened = self.claims.reopen_approved_for_item(item.id)

        self.items.set_status(item, payload.to_status)
        self.items.record_status_event(
            item_id=item.id,
            from_status=current,
            to_status=payload.to_status,
            actor_id=actor.id,
            note=payload.note or (
                "Approval withdrawn; claim reopened." if reopened else None
            ),
        )
        self.notifications.create(
            user_id=item.reporter_id,
            item_id=item.id,
            message=(
                f"'{item.name}' moved from {current.value} to {payload.to_status.value}."
            ),
        )
        for claim in reopened:
            self.notifications.create(
                user_id=claim.claimant_id,
                item_id=item.id,
                message=(
                    f"The approval of your claim on '{item.name}' was withdrawn. "
                    "It is pending again."
                ),
            )
        return self.items.get(item_id)

    def delete(self, item_id: int, actor: User) -> None:
        item = self.get(item_id)
        self._require_reporter(item, actor)
        self.items.delete(item)

    # --- helpers --------------------------------------------------------
    def contact_disclosed_to(self, item: Item, viewer: User | None) -> bool:
        """May `viewer` see the reporter's contact details on this item?

        Only a claimant whose claim on this item has been approved -- the point
        at which the two of them have to arrange a handover. Everyone else,
        signed in or not, sees a name and nothing more.
        """
        if viewer is None or viewer.id == item.reporter_id:
            return False
        if viewer.is_admin:
            return True  # staff arrange handovers that stall
        claim = self.claims.get_for_item_and_user(item.id, viewer.id)
        return claim is not None and claim.status is ClaimStatus.APPROVED

    def _require_reporter(self, item: Item, actor: User) -> None:
        """The reporter owns their item; an admin may act on anyone's.

        Admins exist because the lifecycle otherwise has no oversight at all:
        a reporter decides the claims on their own item, so a wrong call has
        nobody to correct it.
        """
        if item.reporter_id != actor.id and not actor.is_admin:
            raise PermissionDeniedError("Only the reporting user can modify this item.")

    def _validate_refs(self, category_id: int | None, location_id: int | None) -> None:
        if category_id is not None and self.categories.get(category_id) is None:
            raise ValidationError(f"No category with id {category_id}.")
        if location_id is not None and self.locations.get(location_id) is None:
            raise ValidationError(f"No location with id {location_id}.")
