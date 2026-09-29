"""One approved claim per item

Approving a claim is what discloses contact details, so an item with two
approved claims hands two strangers the reporter's address. The service layer
now refuses a second approval; this adds the database-level guarantee behind it:
a partial unique index on ``claims(item_id) WHERE status = 'approved'``.

It also adds ``claims.superseded_by_id``: when an approval auto-rejects the
other pending claims on an item, each records which claim beat it, so that
withdrawing the approval can reopen them.

Existing data may already violate the rule. Rather than silently picking a
winner, the upgrade stops and names the offending items -- which claim stands
is a decision for a person, not a migration.

Revision ID: ed222a032b93
Revises: b052f2f503ff
Create Date: 2026-09-29 19:00:27.636771

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ed222a032b93'
down_revision: Union[str, None] = 'b052f2f503ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _refuse_if_items_have_several_approved_claims() -> None:
    rows = op.get_bind().execute(sa.text(
        "SELECT item_id, count(*) FROM claims WHERE status = 'approved' "
        "GROUP BY item_id HAVING count(*) > 1 ORDER BY item_id"
    )).all()
    if rows:
        detail = ", ".join(f"item {item_id} ({n} approved)" for item_id, n in rows)
        raise RuntimeError(
            f"Cannot add uq_claims_one_approved_per_item: {len(rows)} item(s) "
            f"already have more than one approved claim: {detail}. Decide which "
            "claim stands on each item, set the others to 'rejected', then run "
            "`alembic upgrade head` again."
        )


def upgrade() -> None:
    _refuse_if_items_have_several_approved_claims()

    op.add_column('claims', sa.Column('superseded_by_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'claims_superseded_by_id_fkey', 'claims', 'claims',
        ['superseded_by_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index('ix_claims_superseded_by_id', 'claims', ['superseded_by_id'], unique=False)
    op.create_index(
        'uq_claims_one_approved_per_item', 'claims', ['item_id'], unique=True,
        postgresql_where=sa.text("status = 'approved'"),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_claims_one_approved_per_item', table_name='claims',
        postgresql_where=sa.text("status = 'approved'"),
    )
    op.drop_index('ix_claims_superseded_by_id', table_name='claims')
    op.drop_constraint('claims_superseded_by_id_fkey', 'claims', type_='foreignkey')
    op.drop_column('claims', 'superseded_by_id')
