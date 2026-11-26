from datetime import UTC, datetime
from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, PublicIdMixin


class Client(PublicIdMixin, Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    tax_identifier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rccm: Mapped[str | None] = mapped_column(String(100), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
