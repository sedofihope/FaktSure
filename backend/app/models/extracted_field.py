from datetime import datetime
from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, PublicIdMixin


class ExtractedField(PublicIdMixin, Base):
    __tablename__ = "extracted_fields"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    field_name: Mapped[str] = mapped_column(String(100), index=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="UNCERTAIN")
    source_page: Mapped[int | None] = mapped_column(nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_bbox: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    corrected_at: Mapped[datetime | None] = mapped_column(nullable=True)

    document: Mapped["Document"] = relationship()

    @property
    def document_public_id(self):
        return self.document.public_id
