from datetime import date
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, model_validator


class TaxRuleCreate(BaseModel):
    name: str
    rate: Decimal = Field(ge=0, le=100)
    calculation_type: str = "PERCENTAGE"
    valid_from: date
    valid_until: date | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_period(self):
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("valid_until must not precede valid_from")
        return self


class TaxRuleResponse(TaxRuleCreate):
    public_id: UUID

    model_config = {"from_attributes": True}


class ProductPriceCreate(BaseModel):
    unit_price: Decimal = Field(ge=0)
    currency: str = Field(default="XOF", min_length=3, max_length=3)
    valid_from: date
    valid_until: date | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("valid_until must not precede valid_from")
        return self


class ProductPriceResponse(ProductPriceCreate):
    public_id: UUID
    product_id: UUID = Field(validation_alias="product_public_id")

    model_config = {"from_attributes": True}
