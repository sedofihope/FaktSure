from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InvoiceSequence(Base):
    """Atomic per-year counter used to issue unique invoice numbers."""

    __tablename__ = "invoice_sequences"

    year: Mapped[int] = mapped_column(primary_key=True)
    next_number: Mapped[int] = mapped_column(nullable=False, default=0)
