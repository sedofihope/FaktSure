"""Add public UUIDs to API-facing entities.

Revision ID: a19c7d2ef431
Revises: bf4d2aa5e553
Create Date: 2026-11-25
"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "a19c7d2ef431"
down_revision: Union[str, None] = "bf4d2aa5e553"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = (
    "users",
    "clients",
    "products",
    "product_prices",
    "tax_rules",
    "document_batches",
    "documents",
    "extracted_fields",
    "anomalies",
    "invoices",
    "invoice_items",
    "audit_logs",
)


def upgrade() -> None:
    """Backfill one stable UUID per existing row, then enforce uniqueness."""

    bind = op.get_bind()
    for table_name in TABLES:
        op.add_column(
            table_name,
            sa.Column("public_id", sa.Uuid(as_uuid=True), nullable=True),
        )
        table = sa.Table(
            table_name,
            sa.MetaData(),
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("public_id", sa.Uuid(as_uuid=True)),
        )
        row_ids = bind.execute(sa.select(table.c.id)).scalars().all()
        for row_id in row_ids:
            bind.execute(
                table.update()
                .where(table.c.id == row_id)
                .values(public_id=uuid4())
            )
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "public_id",
                existing_type=sa.Uuid(as_uuid=True),
                nullable=False,
            )
            batch_op.create_index(
                f"ix_{table_name}_public_id",
                ["public_id"],
                unique=True,
            )


def downgrade() -> None:
    """Remove public identifiers without changing internal primary keys."""

    for table_name in reversed(TABLES):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_index(f"ix_{table_name}_public_id")
            batch_op.drop_column("public_id")
