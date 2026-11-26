"""Add an optional invoice-level VAT rule.

Revision ID: 8b7c1d9a42e6
Revises: f0a73c91be42
Create Date: 2026-11-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8b7c1d9a42e6"
down_revision: Union[str, None] = "f0a73c91be42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("invoices")}
    if "tax_rule_id" not in columns:
        with op.batch_alter_table("invoices") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "tax_rule_id",
                    sa.Integer(),
                    sa.ForeignKey("tax_rules.id", name="fk_invoices_tax_rule_id_tax_rules"),
                    nullable=True,
                ),
            )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("invoices")}
    if "tax_rule_id" in columns:
        with op.batch_alter_table("invoices") as batch_op:
            batch_op.drop_column("tax_rule_id")
