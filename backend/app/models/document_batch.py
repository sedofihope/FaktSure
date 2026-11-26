from datetime import UTC, datetime
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base, PublicIdMixin


class DocumentBatch(PublicIdMixin, Base):
    __tablename__ = "document_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    total_documents: Mapped[int] = mapped_column(default=0)
    processed_documents: Mapped[int] = mapped_column(default=0)
    failed_documents: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(30), default="CREATED")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
