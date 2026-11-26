from datetime import UTC, datetime
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, PublicIdMixin


class Anomaly(PublicIdMixin, Base):
    __tablename__ = "anomalies"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    field_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    anomaly_type: Mapped[str] = mapped_column(String(50), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="WARNING")
    description: Mapped[str] = mapped_column(Text)
    expected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))

    document: Mapped["Document"] = relationship()

    @property
    def document_public_id(self):
        return self.document.public_id
