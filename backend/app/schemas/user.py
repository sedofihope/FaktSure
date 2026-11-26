from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200, description="Nom affiché de l'utilisateur.")
    email: EmailStr = Field(description="Adresse e-mail unique, normalisée en minuscules.")
    password: str = Field(min_length=12, max_length=128, description="Mot de passe initial, au moins 12 caractères.")
    role: str = Field(default="ACCOUNTANT", description="Rôle : ADMIN, ACCOUNTANT ou VALIDATOR.")

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"ADMIN", "ACCOUNTANT", "VALIDATOR"}:
            raise ValueError("Role must be ADMIN, ACCOUNTANT, or VALIDATOR")
        return normalized


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200, description="Nouveau nom affiché.")
    role: str | None = Field(default=None, description="Nouveau rôle : ADMIN, ACCOUNTANT ou VALIDATOR.")
    is_active: bool | None = Field(default=None, description="Active ou désactive le compte.")

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.upper()
        if normalized not in {"ADMIN", "ACCOUNTANT", "VALIDATOR"}:
            raise ValueError("Role must be ADMIN, ACCOUNTANT, or VALIDATOR")
        return normalized


class UserResponse(BaseModel):
    public_id: UUID = Field(description="UUID public à utiliser dans les routes.")
    full_name: str = Field(description="Nom affiché.")
    email: str = Field(description="Adresse e-mail du compte.")
    role: str = Field(description="Rôle d'autorisation.")
    is_active: bool = Field(description="Indique si le compte peut se connecter.")

    model_config = {"from_attributes": True}