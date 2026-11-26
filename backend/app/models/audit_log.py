from datetime import UTC, datetime
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, PublicIdMixin


class AuditLog(PublicIdMixin, Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(100), index=True)
    previous_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    user: Mapped["User | None"] = relationship()
