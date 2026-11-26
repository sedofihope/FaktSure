from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application configuration loaded from environment variables."""

    app_name: str = "FaktSure"
    app_env: str = "development"
    database_url: str = "sqlite:///./faktsure.db"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    storage_root: Path = Path("storage/documents")
    r2_enabled: bool = False
    r2_account_id: str = ""
    r2_bucket: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    cloudflare_account_id: str = ""
    cloudflare_api_token: str = ""
    cloudflare_model: str = ""
    document_batch_size: int = 3
    max_document_concurrency: int = 1
    max_upload_size_mb: int = 20
    issuer_name: str = ""
    issuer_address: str = ""
    issuer_tax_identifier: str = ""
    issuer_rccm: str = ""
    issuer_phone: str = ""
    issuer_email: str = ""
    issuer_payment_terms: str = ""
    chromium_executable_path: str = ""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.app_env.lower() == "production":
            if self.jwt_secret == "change-me-in-production" or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be a unique value of at least 32 characters in production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
