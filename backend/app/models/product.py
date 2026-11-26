from datetime import UTC, datetime
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, PublicIdMixin


class Product(PublicIdMixin, Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(30), default="unit")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
