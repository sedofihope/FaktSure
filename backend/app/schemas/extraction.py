from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ExtractedLine(BaseModel):
    description: str | None = Field(default=None, description="Désignation de la ligne.")
    sku: str | None = Field(default=None, description="Référence produit extraite.")
    quantity: Decimal | None = Field(default=None, gt=0, description="Quantité strictement positive.")
    unit: str | None = Field(default=None, description="Unité extraite.")
    unit_price: Decimal | None = Field(default=None, ge=0, description="Prix unitaire hors remise.")
    discount: Decimal | None = Field(default=None, ge=0, description="Montant de remise de la ligne.")
    line_total: Decimal | None = Field(default=None, ge=0, description="Montant net de la ligne.")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confiance estimée entre 0 et 1.")

    model_config = ConfigDict(extra="forbid")


class ExtractionResponse(BaseModel):
    document_type: str | None = Field(default=None, description="Type de pièce détecté.")
    document_number: str | None = Field(default=None, description="Numéro de la pièce source.")
    document_date: str | None = Field(default=None, description="Date extraite au format ISO si interprétable.")
    due_date: str | None = Field(default=None, description="Échéance extraite au format ISO.")
    currency: str | None = Field(default=None, description="Devise extraite, idéalement ISO 4217.")
    payment_terms: str | None = Field(default=None, description="Modalités de paiement extraites.")
    client_name: str | None = Field(default=None, description="Nom du client facturé.")
    client_tax_identifier: str | None = Field(default=None, description="Identifiant fiscal du client.")
    client_rccm: str | None = Field(default=None, description="RCCM du client.")
    client_address: str | None = Field(default=None, description="Adresse du client.")
    client_phone: str | None = Field(default=None, description="Téléphone du client.")
    client_email: str | None = Field(default=None, description="E-mail du client.")
    items: list[ExtractedLine] = Field(default_factory=list, description="Lignes de produit ou service extraites.")
    subtotal: Decimal | None = Field(default=None, description="Sous-total brut avant remises.")
    discount_total: Decimal | None = Field(default=None, description="Total des remises.")
    tax_total: Decimal | None = Field(default=None, description="Total des taxes extraites.")
    grand_total: Decimal | None = Field(default=None, description="Montant total toutes taxes comprises.")

    model_config = ConfigDict(extra="forbid")
