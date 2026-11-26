import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.api.documentation import API_DESCRIPTION, ERROR_RESPONSE, OPERATIONS, TAGS_METADATA
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.schemas.documentation import HealthResponse
import app.models  # noqa: F401 - register SQLAlchemy models


logger = logging.getLogger(__name__)


def configure_cors(app: FastAPI, settings: Settings) -> None:
    """Allow browser requests only from explicitly configured frontend origins."""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.parsed_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["Content-Disposition", "Content-Length"],
    )


def _log_recovery_result(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        return
    except Exception as exc:
        logger.error("Queued batch recovery failed (%s)", type(exc).__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create missing tables only in development; production uses Alembic."""

    if settings.app_env.lower() == "development":
        Base.metadata.create_all(bind=engine)
    from app.core.runtime_settings import load_settings_overrides

    with SessionLocal() as db:
        load_settings_overrides(db)
    recovery_task = None
    from app.services.batch_service import (
        recover_interrupted_batches,
        resume_queued_batches,
    )

    queued_batch_ids = recover_interrupted_batches()
    if queued_batch_ids:
        recovery_task = asyncio.create_task(resume_queued_batches(queued_batch_ids))
        recovery_task.add_done_callback(_log_recovery_result)
    yield
    if recovery_task and not recovery_task.done():
        recovery_task.cancel()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=API_DESCRIPTION,
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
)
configure_cors(app, settings)
register_exception_handlers(app)
from app.api.v1.router import router
app.include_router(router)


def custom_openapi() -> dict:
    """Expose French operation guides and accurate binary upload/download schemas."""

    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    schema["tags"] = TAGS_METADATA
    operation = schema["paths"]["/api/batches/{batch_id}/documents"]["post"]
    request_schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    body_schema = schema["components"]["schemas"][request_schema["$ref"].rsplit("/", 1)[-1]]
    body_schema["properties"]["files"]["items"]["format"] = "binary"
    schema["info"]["description"] = API_DESCRIPTION

    parameter_descriptions = {
        "batch_id": "UUID public du lot, renvoyé lors de sa création.",
        "document_id": "UUID public du document, renvoyé lors de son import.",
        "anomaly_id": "UUID public de l'anomalie, renvoyé dans la liste des anomalies.",
        "client_id": "UUID public du client.",
        "product_id": "UUID public du produit.",
        "invoice_id": "UUID public de la facture ou du brouillon.",
        "user_id": "UUID public de l'utilisateur.",
        "retry_failed": "Inclure les documents en échec lors de la mise en traitement.",
    }
    error_descriptions = {
        401: "Authentification absente, invalide ou expirée.",
        403: "Le rôle de l'utilisateur ne permet pas cette opération.",
        404: "La ressource demandée n'existe pas.",
        409: "L'opération est incompatible avec l'état ou les règles métier.",
        413: "Le fichier dépasse la taille maximale configurée.",
        415: "Le format du fichier n'est pas pris en charge.",
        422: "Le corps, les paramètres ou le fichier ne respectent pas le contrat attendu.",
        503: "Un service ou stockage nécessaire est temporairement indisponible.",
    }
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            documentation = OPERATIONS.get((method, path))
            if documentation is None:
                raise RuntimeError(f"OpenAPI documentation is missing for {method.upper()} {path}")
            summary, description, error_codes = documentation
            operation["summary"] = summary
            operation["description"] = description
            for parameter in operation.get("parameters", []):
                if parameter["name"] in parameter_descriptions:
                    parameter["description"] = parameter_descriptions[parameter["name"]]
            for code in error_codes:
                operation.setdefault("responses", {}).setdefault(
                    str(code),
                    {
                        **ERROR_RESPONSE,
                        "description": error_descriptions[code],
                    },
                )

    preview = schema["paths"]["/api/documents/{document_id}/preview"]["get"]
    preview["responses"]["200"]["description"] = (
        "Contenu binaire du fichier original; le Content-Type correspond au document."
    )
    preview["responses"]["200"]["content"] = {
        "application/pdf": {"schema": {"type": "string", "format": "binary"}},
        "image/*": {"schema": {"type": "string", "format": "binary"}},
    }

    pdf = schema["paths"]["/api/invoices/{invoice_id}/pdf"]["get"]
    pdf["responses"]["200"]["description"] = "Fichier PDF de la facture."
    pdf["responses"]["200"]["content"] = {
        "application/pdf": {"schema": {"type": "string", "format": "binary"}}
    }
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/api/health", tags=["health"], response_model=HealthResponse)
def health() -> dict[str, str]:
    """Return a lightweight health status for monitoring."""

    return {"status": "ok", "environment": settings.app_env}
