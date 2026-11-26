from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class ClientCreate(BaseModel):
    name: str = Field(description="Nom légal ou commercial du client.")
    tax_identifier: str | None = Field(default=None, description="Identifiant fiscal (IFU), facultatif.")
    rccm: str | None = Field(default=None, description="Numéro d'immatriculation RCCM, facultatif.")
    address: str | None = Field(default=None, description="Adresse postale, facultative.")
    phone: str | None = Field(default=None, description="Téléphone de contact, facultatif.")
    email: EmailStr | None = Field(default=None, description="Adresse e-mail valide, facultative.")


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, description="Nouveau nom légal ou commercial.")
    tax_identifier: str | None = Field(default=None, description="Nouvel IFU, ou null pour effacer.")
    rccm: str | None = Field(default=None, description="Nouveau RCCM, ou null pour effacer.")
    address: str | None = Field(default=None, description="Nouvelle adresse, ou null pour effacer.")
    phone: str | None = Field(default=None, description="Nouveau téléphone, ou null pour effacer.")
    email: EmailStr | None = Field(default=None, description="Nouvelle adresse e-mail, ou null pour effacer.")
    is_active: bool | None = Field(default=None, description="Activer ou désactiver la fiche.")


class ClientResponse(ClientCreate):
    public_id: UUID = Field(description="UUID public à utiliser dans les routes.")
    is_active: bool = Field(description="False signifie que le client n'est pas proposé pour une nouvelle facture.")

    model_config = {"from_attributes": True}
