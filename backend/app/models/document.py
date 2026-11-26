from datetime import UTC, datetime
from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, PublicIdMixin


class Document(PublicIdMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("batch_id", "sha256", name="uq_document_batch_sha"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("document_batches.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int]
    document_type: Mapped[str] = mapped_column(String(30), default="UNSUPPORTED")
    classification_confidence: Mapped[float] = mapped_column(default=0.0)
    processing_engine: Mapped[str | None] = mapped_column(String(100), nullable=True)
    storage_backend: Mapped[str] = mapped_column(String(30), default="local")
    storage_key: Mapped[str]
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30), default="UPLOADED")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    batch: Mapped["DocumentBatch"] = relationship()

    @property
    def batch_public_id(self):
        return self.batch.public_id
