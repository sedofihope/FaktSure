from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr = Field(description="Adresse e-mail du compte.")
    password: str = Field(
        min_length=1,
        max_length=128,
        description="Mot de passe associé au compte.",
    )


class TokenResponse(BaseModel):
    access_token: str = Field(description="Jeton JWT à transmettre dans Authorization.")
    token_type: str = Field(default="bearer", description="Type d'authentification du jeton.")
