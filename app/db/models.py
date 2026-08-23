"""Relational schema for the campus lost & found service.

Normalisation notes
-------------------
* ``locations`` is its own table with a foreign key from ``items`` -- location is
  not a free-text column hanging off a flat items table.
* ``claims`` is its own table linking an item to the user claiming it, carrying
  its own decision state and audit columns.
* ``item_status_events`` records every lifecycle transition, so an item's history
  is queryable rather than being overwritten in place.

Indexing notes
--------------
The search endpoint filters ``items.name``/``items.description`` with a
leading-wildcard ILIKE, which a plain btree index cannot serve. Those two columns
therefore get **pg_trgm GIN** indexes. The equality/enum filters (category,
location, status, kind) get ordinary btree indexes, which do help.
"""
from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.lifecycle import ItemKind, ItemStatus


def _pg_enum(enum_cls: type, name: str) -> SAEnum:
    """Native PG enum that stores the lowercase *values*, not the member names."""
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda cls: [member.value for member in cls],
        native_enum=True,
    )


class ClaimStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class OtpPurpose(str, enum.Enum):
    REGISTRATION = "registration"
    PASSWORD_RESET = "password_reset"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(String(50), nullable=False)
    last_name: Mapped[str] = mapped_column(String(50), nullable=False)
    roll_number: Mapped[str] = mapped_column(String(20), nullable=False)
    batch: Mapped[int] = mapped_column(nullable=False)
    course: Mapped[str] = mapped_column(String(10), nullable=False)
    branch: Mapped[str] = mapped_column(String(10), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    reported_items: Mapped[list["Item"]] = relationship(
        back_populates="reporter", foreign_keys="Item.reporter_id"
    )
    claims: Mapped[list["Claim"]] = relationship(
        back_populates="claimant", foreign_keys="Claim.claimant_id"
    )


class Location(Base, TimestampMixin):
    """A place on campus. Normalised out of ``items``."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    building: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list["Item"]] = relationship(back_populates="location")

    __table_args__ = (
        UniqueConstraint("name", "building", name="uq_locations_name_building"),
        Index(
            "ix_locations_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )


class Category(Base, TimestampMixin):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    items: Mapped[list["Item"]] = relationship(back_populates="category")


class Item(Base, TimestampMixin):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    kind: Mapped[ItemKind] = mapped_column(
        _pg_enum(ItemKind, "item_kind"), nullable=False
    )
    status: Mapped[ItemStatus] = mapped_column(
        _pg_enum(ItemStatus, "item_status"),
        nullable=False,
        default=ItemStatus.REPORTED,
        server_default=ItemStatus.REPORTED.value,
    )

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL")
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    reporter_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    image_path: Mapped[str | None] = mapped_column(String(255))
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)

    category: Mapped["Category | None"] = relationship(back_populates="items")
    location: Mapped["Location | None"] = relationship(back_populates="items")
    reporter: Mapped["User"] = relationship(
        back_populates="reported_items", foreign_keys=[reporter_id]
    )
    claims: Mapped[list["Claim"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
    status_events: Mapped[list["ItemStatusEvent"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Leading-wildcard ILIKE on these two columns is the search hot path;
        # btree cannot serve it, so index them with pg_trgm GIN.
        # The opclass goes in postgresql_ops (not inline in a text() clause) so
        # Alembic can diff these indexes and detect drift.
        Index(
            "ix_items_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "ix_items_description_trgm",
            "description",
            postgresql_using="gin",
            postgresql_ops={"description": "gin_trgm_ops"},
        ),
        # Equality / enum filters on the same search endpoint.
        Index("ix_items_category_id", "category_id"),
        Index("ix_items_location_id", "location_id"),
        Index("ix_items_status", "status"),
        Index("ix_items_kind", "kind"),
        Index("ix_items_reporter_id", "reporter_id"),
        Index("ix_items_occurred_on", "occurred_on"),
        # Common combined filter: "open found items", newest first.
        Index("ix_items_status_kind_occurred", "status", "kind", "occurred_on"),
    )


class Claim(Base, TimestampMixin):
    """Someone asserting ownership of an item. Its own entity, not a boolean."""

    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    claimant_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[ClaimStatus] = mapped_column(
        _pg_enum(ClaimStatus, "claim_status"),
        nullable=False,
        default=ClaimStatus.PENDING,
        server_default=ClaimStatus.PENDING.value,
    )
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    item: Mapped["Item"] = relationship(back_populates="claims")
    claimant: Mapped["User"] = relationship(
        back_populates="claims", foreign_keys=[claimant_id]
    )

    __table_args__ = (
        UniqueConstraint("item_id", "claimant_id", name="uq_claims_item_claimant"),
        Index("ix_claims_item_id", "item_id"),
        Index("ix_claims_claimant_id", "claimant_id"),
        Index("ix_claims_status", "status"),
    )


class ItemStatusEvent(Base):
    """Append-only audit of lifecycle transitions."""

    __tablename__ = "item_status_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[ItemStatus | None] = mapped_column(
        _pg_enum(ItemStatus, "item_status")
    )
    to_status: Mapped[ItemStatus] = mapped_column(
        _pg_enum(ItemStatus, "item_status"), nullable=False
    )
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    item: Mapped["Item"] = relationship(back_populates="status_events")

    __table_args__ = (Index("ix_item_status_events_item_id", "item_id"),)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    message: Mapped[str] = mapped_column(String(255), nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (Index("ix_notifications_user_id", "user_id"),)


class OtpToken(Base):
    """One-time codes for registration verification and password reset."""

    __tablename__ = "otp_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[OtpPurpose] = mapped_column(
        _pg_enum(OtpPurpose, "otp_purpose"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        Index("ix_otp_tokens_user_purpose", "user_id", "purpose"),
    )
