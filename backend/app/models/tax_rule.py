from datetime import date
from decimal import Decimal
from sqlalchemy import Boolean, Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, PublicIdMixin


class TaxRule(PublicIdMixin, Base):
    __tablename__ = "tax_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    rate: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    calculation_type: Mapped[str] = mapped_column(String(30), default="PERCENTAGE")
    valid_from: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
