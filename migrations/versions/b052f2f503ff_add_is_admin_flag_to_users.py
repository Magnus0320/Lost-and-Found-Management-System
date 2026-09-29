"""Add is_admin flag to users

Staff flag for the oversight role. Defaults false at the database level so
every existing row -- and every future registration -- is a plain user unless
someone is deliberately promoted.

Revision ID: b052f2f503ff
Revises: ac938cefe45e
Create Date: 2026-09-15 17:47:17.550025

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b052f2f503ff'
down_revision: Union[str, None] = 'ac938cefe45e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'is_admin')
