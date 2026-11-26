from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ExtractedLine(BaseModel):
    description: str | None = None
    sku: str | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    unit: str | None = None
    unit_price: Decimal | None = Field(default=None, ge=0)
    discount: Decimal | None = Field(default=None, ge=0)
    line_total: Decimal | None = Field(default=None, ge=0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    model_config = ConfigDict(extra="forbid")


class ExtractionResponse(BaseModel):
    document_type: str | None = None
    document_number: str | None = None
    document_date: str | None = None
    due_date: str | None = None
    currency: str | None = None
    payment_terms: str | None = None
    client_name: str | None = None
    client_tax_identifier: str | None = None
    client_rccm: str | None = None
    client_address: str | None = None
    client_phone: str | None = None
    client_email: str | None = None
    items: list[ExtractedLine] = Field(default_factory=list)
    subtotal: Decimal | None = None
    discount_total: Decimal | None = None
    tax_total: Decimal | None = None
    grand_total: Decimal | None = None

    model_config = ConfigDict(extra="forbid")
