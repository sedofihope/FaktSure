from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    role: str = "ACCOUNTANT"

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"ADMIN", "ACCOUNTANT", "VALIDATOR"}:
            raise ValueError("Role must be ADMIN, ACCOUNTANT, or VALIDATOR")
        return normalized


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = None
    is_active: bool | None = None

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
    public_id: UUID
    full_name: str
    email: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}