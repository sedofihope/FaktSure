from datetime import date
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, model_validator


class TaxRuleCreate(BaseModel):
    name: str = Field(description="Libellé de la règle, par exemple TVA.")
    rate: Decimal = Field(ge=0, le=100, description="Taux en pourcentage, entre 0 et 100.")
    calculation_type: str = Field(default="PERCENTAGE", description="Type de calcul actuellement pris en charge : PERCENTAGE.")
    valid_from: date = Field(description="Premier jour d'application inclus, format YYYY-MM-DD.")
    valid_until: date | None = Field(default=None, description="Dernier jour d'application inclus; null signifie sans date de fin.")
    is_active: bool = Field(default=True, description="Désactive la règle sans la supprimer.")

    @model_validator(mode="after")
    def validate_period(self):
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("valid_until must not precede valid_from")
        return self


class TaxRuleResponse(TaxRuleCreate):
    public_id: UUID

    model_config = {"from_attributes": True}


class ProductPriceCreate(BaseModel):
    unit_price: Decimal = Field(ge=0, description="Prix unitaire hors taxe, supérieur ou égal à zéro.")
    currency: str = Field(default="XOF", min_length=3, max_length=3, description="Code devise ISO 4217, par défaut XOF.")
    valid_from: date = Field(description="Premier jour de validité inclus.")
    valid_until: date | None = Field(default=None, description="Dernier jour inclus; null signifie prix sans date de fin.")

    @model_validator(mode="after")
    def validate_period(self):
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("valid_until must not precede valid_from")
        return self


class ProductPriceResponse(ProductPriceCreate):
    public_id: UUID
    product_id: UUID = Field(validation_alias="product_public_id")

    model_config = {"from_attributes": True}
