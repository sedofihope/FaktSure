from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.utils.number_formatting import format_decimal


class InvoiceItemCreate(BaseModel):
    product_id: UUID | None = None
    description: str
    quantity: Decimal = Field(gt=0)
    unit: str = "unit"
    unit_price: Decimal = Field(ge=0)
    discount: Decimal = Field(default=Decimal("0"), ge=0)
    tax_rule_id: UUID | None = None


class InvoiceCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "document_id": "8c4a4b9e-4e51-46c1-8c4a-9b9f1d45a4c2",
        }
    })

    document_id: UUID
    client_id: UUID | None = Field(
        default=None,
        description="Optional when the reviewed document identifies one matching active client.",
    )
    issue_date: date | None = Field(
        default=None,
        description="Optional invoice date; defaults to today, not the source order/quote date.",
    )
    due_date: date | None = Field(
        default=None,
        description="Optional invoice due date. Source order/quote dates are not reused.",
    )
    payment_terms: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional payment terms; defaults to terms extracted from the reviewed document.",
    )
    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=10,
        description="Optional override; defaults to the extracted document currency.",
    )
    items: list[InvoiceItemCreate] | None = Field(
        default=None,
        min_length=1,
        description="Omit to build lines and totals from reviewed extracted fields. Provide to manually override the extracted lines.",
    )


class InvoiceUpdate(BaseModel):
    due_date: date | None = None


class InvoiceResponse(BaseModel):
    public_id: UUID
    document_id: UUID = Field(validation_alias="document_public_id")
    client_id: UUID | None = Field(validation_alias="client_public_id")
    invoice_number: str
    issue_date: date
    due_date: date | None
    payment_terms: str | None
    currency: str
    subtotal: Decimal
    discount_total: Decimal
    tax_total: Decimal
    grand_total: Decimal
    status: str

    model_config = {"from_attributes": True}

    @field_serializer(
        "subtotal",
        "discount_total",
        "tax_total",
        "grand_total",
        when_used="json",
    )
    def serialize_amount(self, value: Decimal) -> str:
        return format_decimal(value)
