"""Add RCCM to clients.

Revision ID: c72e4a91d630
Revises: a19c7d2ef431
Create Date: 2026-11-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c72e4a91d630"
down_revision: Union[str, None] = "a19c7d2ef431"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("rccm", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("clients", "rccm")
