from uuid import UUID

from pydantic import BaseModel, EmailStr


class ClientCreate(BaseModel):
    name: str
    tax_identifier: str | None = None
    rccm: str | None = None
    address: str | None = None
    phone: str | None = None
    email: EmailStr | None = None


class ClientUpdate(BaseModel):
    name: str | None = None
    tax_identifier: str | None = None
    rccm: str | None = None
    address: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    is_active: bool | None = None


class ClientResponse(ClientCreate):
    public_id: UUID
    is_active: bool

    model_config = {"from_attributes": True}
