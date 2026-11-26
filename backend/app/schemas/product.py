from uuid import UUID

from pydantic import BaseModel


class ProductCreate(BaseModel):
    sku: str | None = None
    name: str
    description: str | None = None
    unit: str = "unit"


class ProductUpdate(BaseModel):
    sku: str | None = None
    name: str | None = None
    description: str | None = None
    unit: str | None = None
    is_active: bool | None = None


class ProductResponse(ProductCreate):
    public_id: UUID
    is_active: bool

    model_config = {"from_attributes": True}
