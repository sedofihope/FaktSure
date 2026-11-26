from datetime import UTC, datetime, date
from decimal import Decimal
from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, PublicIdMixin


class ProductPrice(PublicIdMixin, Base):
    __tablename__ = "product_prices"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    currency: Mapped[str] = mapped_column(String(3))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    product: Mapped["Product"] = relationship()

    @property
    def product_public_id(self):
        return self.product.public_id
