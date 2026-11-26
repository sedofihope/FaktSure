"""Add invoice payment terms and persistent runtime settings.

Revision ID: f0a73c91be42
Revises: e29c6f4a1b73
Create Date: 2026-11-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f0a73c91be42"
down_revision: Union[str, None] = "e29c6f4a1b73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    invoice_columns = {column["name"] for column in inspector.get_columns("invoices")}
    if "payment_terms" not in invoice_columns:
        op.add_column(
            "invoices",
            sa.Column("payment_terms", sa.Text(), nullable=True),
        )

    if "app_settings" not in inspector.get_table_names():
        op.create_table(
            "app_settings",
            sa.Column("key", sa.String(length=100), primary_key=True),
            sa.Column("value", sa.Text(), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_column("invoices", "payment_terms")
