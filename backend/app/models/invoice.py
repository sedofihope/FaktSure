from datetime import UTC, datetime, date
from decimal import Decimal
from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, PublicIdMixin


class Invoice(PublicIdMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("document_id", name="uq_invoice_document"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"), nullable=True)
    tax_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("tax_rules.id", name="fk_invoices_tax_rule_id_tax_rules"),
        nullable=True,
    )
    invoice_number: Mapped[str] = mapped_column(String(100), unique=True)
    issue_date: Mapped[date]
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="XOF")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    discount_total: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    pdf_storage_backend: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pdf_storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pdf_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pdf_format_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    validated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    document: Mapped["Document"] = relationship()
    client: Mapped["Client | None"] = relationship()
    tax_rule: Mapped["TaxRule | None"] = relationship()

    @property
    def document_public_id(self):
        return self.document.public_id

    @property
    def client_public_id(self):
        return self.client.public_id if self.client else None

    @property
    def tax_rule_public_id(self):
        return self.tax_rule.public_id if self.tax_rule else None
