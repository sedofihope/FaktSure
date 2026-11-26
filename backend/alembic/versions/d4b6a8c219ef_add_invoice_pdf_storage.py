"""Add persistent PDF storage metadata to invoices.

Revision ID: d4b6a8c219ef
Revises: c72e4a91d630
Create Date: 2026-11-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4b6a8c219ef"
down_revision: Union[str, None] = "c72e4a91d630"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("pdf_storage_backend", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("pdf_storage_key", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("pdf_sha256", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invoices", "pdf_sha256")
    op.drop_column("invoices", "pdf_storage_key")
    op.drop_column("invoices", "pdf_storage_backend")
