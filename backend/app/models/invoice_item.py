from decimal import Decimal
from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, PublicIdMixin


class InvoiceItem(PublicIdMixin, Base):
    __tablename__ = "invoice_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    unit: Mapped[str] = mapped_column(String(30), default="unit")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    discount: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    tax_rule_id: Mapped[int | None] = mapped_column(ForeignKey("tax_rules.id"), nullable=True)
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 6))
