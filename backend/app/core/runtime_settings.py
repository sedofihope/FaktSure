from threading import RLock

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.app_setting import AppSetting

_lock = RLock()
_overrides: dict[str, object] = {}


def load_settings_overrides(db: Session) -> None:
    """Load persisted non-secret settings into this process."""

    rows = db.scalars(select(AppSetting)).all()
    parsed: dict[str, object] = {}
    for row in rows:
        if row.key in {"document_batch_size", "max_document_concurrency", "max_upload_size_mb"}:
            parsed[row.key] = int(row.value)
        elif row.key == "r2_enabled":
            parsed[row.key] = row.value == "true"
        elif row.key in {"llm_provider", "gemini_model", "groq_model", "cloudflare_model"}:
            parsed[row.key] = row.value
        elif row.key in {
            "issuer_name",
            "issuer_address",
            "issuer_tax_identifier",
            "issuer_rccm",
            "issuer_phone",
            "issuer_email",
            "issuer_payment_terms",
        }:
            parsed[row.key] = row.value
    with _lock:
        _overrides.clear()
        _overrides.update(parsed)


def update_settings_overrides(values: dict[str, object]) -> None:
    with _lock:
        _overrides.update(values)


def get_runtime_settings() -> Settings:
    with _lock:
        overrides = dict(_overrides)
    return get_settings().model_copy(update=overrides)


def reset_settings_overrides() -> None:
    with _lock:
        _overrides.clear()
