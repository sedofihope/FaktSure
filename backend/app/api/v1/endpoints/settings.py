import json
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError
from app.core.permissions import require_roles
from app.core.runtime_settings import get_runtime_settings, update_settings_overrides
from app.db.session import get_db
from app.models.app_setting import AppSetting
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.documentation import IssuerSettingsResponse, SettingsResponse, SettingsUpdateResponse

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


class IssuerSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None,
        max_length=200,
        description="Nom légal de l'émetteur; null ou vide efface la valeur.",
    )
    address: str | None = Field(default=None, max_length=500, description="Adresse de l'émetteur.")
    tax_identifier: str | None = Field(default=None, max_length=100, description="Identifiant fiscal (IFU).")
    rccm: str | None = Field(default=None, max_length=100, description="Numéro RCCM.")
    phone: str | None = Field(default=None, max_length=100, description="Téléphone de l'émetteur.")
    email: EmailStr | None = Field(
        default=None,
        description="Adresse e-mail; null ou vide efface la valeur.",
    )
    payment_terms: str | None = Field(
        default=None,
        max_length=500,
        description="Modalités de paiement par défaut.",
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_empty_email(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("name", "address", "tax_identifier", "rccm", "phone", "payment_terms")
    @classmethod
    def trim_text_fields(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("Au moins une information de l'émetteur doit être fournie.")
        return self


def _persist(
    db: Session,
    values: dict[str, object],
    *,
    audit_user: User | None = None,
    audit_previous: dict[str, str] | None = None,
) -> None:
    for key, value in values.items():
        setting = db.get(AppSetting, key)
        if setting is None:
            setting = AppSetting(key=key, value=str(value).lower() if isinstance(value, bool) else str(value))
            db.add(setting)
        else:
            setting.value = str(value).lower() if isinstance(value, bool) else str(value)
    if audit_user is not None and audit_previous is not None:
        db.add(AuditLog(
            user_id=audit_user.id,
            action="ISSUER_SETTINGS_UPDATED",
            entity_type="app_settings",
            entity_id="issuer",
            previous_value=json.dumps(audit_previous, ensure_ascii=False, sort_keys=True),
            new_value=json.dumps(
                {key: str(value) for key, value in values.items()},
                ensure_ascii=False,
                sort_keys=True,
            ),
        ))
    db.commit()
    update_settings_overrides(values)


def _issuer_values(settings: Settings) -> dict[str, str]:
    return {
        "name": settings.issuer_name,
        "address": settings.issuer_address,
        "tax_identifier": settings.issuer_tax_identifier,
        "rccm": settings.issuer_rccm,
        "phone": settings.issuer_phone,
        "email": settings.issuer_email,
        "payment_terms": settings.issuer_payment_terms,
    }


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
        "issuer": _issuer_values(settings),
    }

@router.put("/issuer", response_model=SettingsUpdateResponse)
def update_issuer_settings(
    payload: IssuerSettingsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN")),
):
    settings = get_runtime_settings()
    previous = _issuer_values(settings)
    issuer_fields = {
        "name": "issuer_name",
        "address": "issuer_address",
        "tax_identifier": "issuer_tax_identifier",
        "rccm": "issuer_rccm",
        "phone": "issuer_phone",
        "email": "issuer_email",
        "payment_terms": "issuer_payment_terms",
    }
    values = {
        issuer_fields[field]: (str(value) if value is not None else "")
        for field, value in payload.model_dump(exclude_unset=True).items()
    }
    audit_previous = {
        issuer_fields[field]: previous[field]
        for field in payload.model_fields_set
    }
    _persist(db, values, audit_user=user, audit_previous=audit_previous)
    return {
        "status": "updated",
        "issuer": IssuerSettingsResponse(**_issuer_values(get_runtime_settings())),
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
