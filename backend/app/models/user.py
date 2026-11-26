from datetime import UTC, datetime
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, PublicIdMixin


class User(PublicIdMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="ACCOUNTANT")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
