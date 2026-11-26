from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.core.permissions import require_roles
from app.core.runtime_settings import get_runtime_settings, update_settings_overrides
from app.db.session import get_db
from app.models.app_setting import AppSetting
from app.models.user import User
from app.schemas.documentation import SettingsResponse, SettingsUpdateResponse

router = APIRouter(prefix="/settings", tags=["settings"])


class ProcessingSettingsUpdate(BaseModel):
    document_batch_size: int = Field(
        ge=1,
        le=100,
        description="Nombre de documents regroupés dans un lot interne (1 à 100).",
    )
    max_document_concurrency: int = Field(
        ge=1,
        le=32,
        description="Nombre maximal de documents traités simultanément (1 à 32).",
    )
    max_upload_size_mb: int = Field(
        ge=1,
        le=500,
        description="Taille maximale acceptée par fichier, en Mo (1 à 500).",
    )


class AISettingsUpdate(BaseModel):
    provider: Literal["gemini", "groq", "cloudflare"] = Field(
        description="Fournisseur dont les identifiants sont déjà définis dans l'environnement.",
    )
    model: str = Field(
        min_length=1,
        max_length=200,
        description="Identifiant du modèle à utiliser auprès du fournisseur.",
    )


class StorageSettingsUpdate(BaseModel):
    backend: Literal["local", "r2"] = Field(
        description="Backend de stockage des fichiers : local ou R2.",
    )


def _persist(db: Session, values: dict[str, object]) -> None:
    for key, value in values.items():
        setting = db.get(AppSetting, key)
        if setting is None:
            setting = AppSetting(key=key, value=str(value).lower() if isinstance(value, bool) else str(value))
            db.add(setting)
        else:
            setting.value = str(value).lower() if isinstance(value, bool) else str(value)
    db.commit()
    update_settings_overrides(values)


@router.get("", response_model=SettingsResponse)
def read_settings(
    _user: User = Depends(require_roles("ADMIN")),
):
    settings = get_runtime_settings()
    models = {
        "gemini": settings.gemini_model,
        "groq": settings.groq_model,
        "cloudflare": settings.cloudflare_model,
    }
    configured = {
        "gemini": bool(settings.gemini_api_key),
        "groq": bool(settings.groq_api_key),
        "cloudflare": bool(settings.cloudflare_account_id and settings.cloudflare_api_token),
    }
    return {
        "processing": {
            "document_batch_size": settings.document_batch_size,
            "max_document_concurrency": settings.max_document_concurrency,
            "max_upload_size_mb": settings.max_upload_size_mb,
        },
        "ai": {
            "provider": settings.llm_provider,
            "model": models[settings.llm_provider],
            "configured": configured[settings.llm_provider],
            "available_providers": configured,
        },
        "storage": {
            "backend": "r2" if settings.r2_enabled else "local",
            "r2_configured": bool(
                settings.r2_account_id
                and settings.r2_bucket
                and settings.r2_access_key_id
                and settings.r2_secret_access_key
            ),
        },
        "issuer": {
            "name": settings.issuer_name,
            "address": settings.issuer_address,
            "tax_identifier": settings.issuer_tax_identifier,
            "rccm": settings.issuer_rccm,
            "phone": settings.issuer_phone,
            "email": settings.issuer_email,
            "payment_terms": settings.issuer_payment_terms,
        },
    }


@router.put("/processing", response_model=SettingsUpdateResponse)
def update_processing_settings(
    payload: ProcessingSettingsUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("ADMIN")),
):
    values = payload.model_dump()
    _persist(db, values)
    return {"status": "updated", "processing": values}


@router.put("/ai", response_model=SettingsUpdateResponse)
def update_ai_settings(
    payload: AISettingsUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("ADMIN")),
):
    settings = get_runtime_settings()
    credentials = {
        "gemini": bool(settings.gemini_api_key),
        "groq": bool(settings.groq_api_key),
        "cloudflare": bool(settings.cloudflare_account_id and settings.cloudflare_api_token),
    }
    if not credentials[payload.provider]:
        raise ConflictError(
            f"{payload.provider} credentials must be configured in the environment before selecting it"
        )
    model_key = f"{payload.provider}_model"
    values = {"llm_provider": payload.provider, model_key: payload.model}
    _persist(db, values)
    return {"status": "updated", "provider": payload.provider, "model": payload.model}


@router.put("/storage", response_model=SettingsUpdateResponse)
def update_storage_settings(
    payload: StorageSettingsUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("ADMIN")),
):
    settings = get_runtime_settings()
    if payload.backend == "r2" and not all((
        settings.r2_account_id,
        settings.r2_bucket,
        settings.r2_access_key_id,
        settings.r2_secret_access_key,
    )):
        raise ConflictError(
            "R2 credentials must be configured in the environment before selecting R2"
        )
    enabled = payload.backend == "r2"
    _persist(db, {"r2_enabled": enabled})
    return {"status": "updated", "backend": payload.backend}
