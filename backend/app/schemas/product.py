from uuid import UUID

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    sku: str | None = Field(default=None, description="Référence SKU unique si renseignée.")
    name: str = Field(description="Nom du produit ou service.")
    description: str | None = Field(default=None, description="Description facultative.")
    unit: str = Field(default="unit", description="Unité de mesure ou de facturation.")


class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, description="Nouveau SKU, ou null pour effacer.")
    name: str | None = Field(default=None, description="Nouveau nom.")
    description: str | None = Field(default=None, description="Nouvelle description, ou null pour effacer.")
    unit: str | None = Field(default=None, description="Nouvelle unité.")
    is_active: bool | None = Field(default=None, description="Activer ou désactiver le produit.")


class ProductResponse(ProductCreate):
    public_id: UUID = Field(description="UUID public à utiliser dans les routes.")
    is_active: bool = Field(description="False signifie que le produit n'est plus proposé.")

    model_config = {"from_attributes": True}
