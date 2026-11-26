from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.utils.number_formatting import format_decimal


class InvoiceItemCreate(BaseModel):
    product_id: UUID | None = Field(default=None, description="UUID public d'un produit actif, facultatif.")
    description: str = Field(description="Désignation affichée sur la facture.")
    quantity: Decimal = Field(gt=0, description="Quantité strictement positive.")
    unit: str = Field(default="unit", description="Unité affichée.")
    unit_price: Decimal = Field(ge=0, description="Prix unitaire avant remise.")
    discount: Decimal = Field(default=Decimal("0"), ge=0, description="Remise monétaire de la ligne.")
    tax_rule_id: UUID | None = Field(default=None, description="UUID public de la règle fiscale applicable.")


class InvoiceCreate(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "document_id": "8c4a4b9e-4e51-46c1-8c4a-9b9f1d45a4c2",
        }
    })

    document_id: UUID = Field(description="UUID public d'un document en état READY.")
    client_id: UUID | None = Field(
        default=None,
        description="UUID public du client actif; facultatif si le rapprochement du document est non ambigu.",
    )
    issue_date: date | None = Field(
        default=None,
        description="Date d'émission (YYYY-MM-DD); par défaut aujourd'hui, jamais la date d'un devis/bon de commande.",
    )
    due_date: date | None = Field(
        default=None,
        description="Date d'échéance (YYYY-MM-DD); reste vide si absente.",
    )
    payment_terms: str | None = Field(
        default=None,
        max_length=2000,
        description="Modalités de paiement; valeur extraite utilisée par défaut si disponible.",
    )
    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=10,
        description="Code devise de remplacement; par défaut la devise extraite, convertie si nécessaire en code ISO.",
    )
    items: list[InvoiceItemCreate] | None = Field(
        default=None,
        min_length=1,
        description="Omettre pour utiliser les lignes extraites; fournir une liste pour remplacer intégralement ces lignes.",
    )


class InvoiceUpdate(BaseModel):
    due_date: date | None = Field(default=None, description="Nouvelle échéance; seule propriété modifiable sur un brouillon.")


class InvoiceResponse(BaseModel):
    public_id: UUID = Field(description="UUID public à utiliser dans les routes.")
    document_id: UUID = Field(validation_alias="document_public_id", description="UUID public du document source.")
    client_id: UUID | None = Field(validation_alias="client_public_id", description="UUID public du client associé.")
    invoice_number: str = Field(description="Référence provisoire du brouillon ou numéro définitif après émission.")
    issue_date: date = Field(description="Date d'émission.")
    due_date: date | None = Field(description="Échéance éventuelle.")
    payment_terms: str | None = Field(description="Modalités de paiement.")
    currency: str = Field(description="Code devise ISO 4217.")
    subtotal: Decimal = Field(description="Sous-total brut avant remises.")
    discount_total: Decimal = Field(description="Montant total des remises.")
    tax_total: Decimal = Field(description="Montant total des taxes recalculées.")
    grand_total: Decimal = Field(description="Total final : sous-total - remises + taxes.")
    status: str = Field(description="État : DRAFT, PENDING_VALIDATION ou ISSUED.")

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
