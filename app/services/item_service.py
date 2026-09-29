from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from app.db.models import ClaimStatus, Item, User
from app.lifecycle import ItemKind, ItemStatus, IllegalTransition, assert_transition
from app.repositories.claim_repo import ClaimRepository
from app.repositories.item_repo import ItemRepository
from app.repositories.location_repo import CategoryRepository, LocationRepository
from app.repositories.notification_repo import NotificationRepository


#: Match suggestions: a lost item is compared with found items and vice versa.
#: Text similarity is pg_trgm's, blended 60/40 between name-vs-name and the
#: full text. Names discriminate far better -- descriptions are prose, and
#: unrelated prose shares enough common trigrams to score 0.15-0.25 -- so they
#: carry most of the weight. Genuine pairs measured 0.38-0.55 on this blend,
#: unrelated ones at most ~0.17, hence the 0.25 cut-off.
SUGGESTION_LIMIT = 5
SUGGESTION_NAME_WEIGHT = 0.6
SUGGESTION_MIN_SIMILARITY = 0.25
SUGGESTION_CATEGORY_BOOST = 0.10
SUGGESTION_LOCATION_BOOST = 0.05
SUGGESTION_DATE_BOOST = 0.05
SUGGESTION_DATE_WINDOW = timedelta(days=14)

_OPPOSITE = {ItemKind.LOST: ItemKind.FOUND, ItemKind.FOUND: ItemKind.LOST}


@dataclass(frozen=True)
class Suggestion:
    item: Item
    score: float
    similarity: float
    reasons: tuple[str, ...]


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
        # Locked like a claim decision, since moving out of `claimed` rewrites
        # the item's claims too.
        item = self.items.get_for_update(item_id)
        if item is None:
            raise NotFoundError(f"No item with id {item_id}.")
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
        #
        # The claims that approval auto-rejected are reopened with it: they lost
        # to the approved claim, not on their own merits, and a decided claim can
        # never be decided again -- so leaving them rejected would lock out what
        # may be the real owner for good.
        reopened, revived = [], []
        if current is ItemStatus.CLAIMED and payload.to_status is not ItemStatus.CLOSED:
            reopened = self.claims.reopen_approved_for_item(item.id)
            revived = self.claims.reopen_superseded_by([c.id for c in reopened])

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
        for claim in revived:
            self.notifications.create(
                user_id=claim.claimant_id,
                item_id=item.id,
                message=(
                    f"The claim approved on '{item.name}' was withdrawn, so yours "
                    "is pending again."
                ),
            )
        return self.items.get(item_id)

    def suggest_matches(self, item_id: int, limit: int = SUGGESTION_LIMIT) -> list[Suggestion]:
        """Items of the opposite kind that may be the same object.

        Excludes closed items and the reporter's own posts. A closed item has
        been resolved, so it gets no suggestions either.
        """
        item = self.get(item_id)
        if item.status is ItemStatus.CLOSED:
            return []
        rows = self.items.suggest_matches(
            item,
            kind=_OPPOSITE[item.kind],
            name_weight=SUGGESTION_NAME_WEIGHT,
            min_similarity=SUGGESTION_MIN_SIMILARITY,
            category_boost=SUGGESTION_CATEGORY_BOOST,
            location_boost=SUGGESTION_LOCATION_BOOST,
            date_boost=SUGGESTION_DATE_BOOST,
            date_from=item.occurred_on - SUGGESTION_DATE_WINDOW,
            date_to=item.occurred_on + SUGGESTION_DATE_WINDOW,
            limit=min(limit, SUGGESTION_LIMIT),
        )
        suggestions = []
        for match, score, similarity, same_category, same_location, close_date in rows:
            reasons = [
                label for label, hit in (
                    ("same category", same_category),
                    ("same location", same_location),
                    (f"within {SUGGESTION_DATE_WINDOW.days} days", close_date),
                ) if hit
            ]
            suggestions.append(Suggestion(
                item=match,
                score=round(float(score), 3),
                similarity=round(float(similarity), 3),
                reasons=tuple(reasons),
            ))
        return suggestions

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
