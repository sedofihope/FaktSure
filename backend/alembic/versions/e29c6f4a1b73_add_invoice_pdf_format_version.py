"""Track invoice PDF rendering format version.

Revision ID: e29c6f4a1b73
Revises: d4b6a8c219ef
Create Date: 2026-11-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e29c6f4a1b73"
down_revision: Union[str, None] = "d4b6a8c219ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("pdf_format_version", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invoices", "pdf_format_version")
