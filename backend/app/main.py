import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.db.base import Base
from app.db.session import SessionLocal, engine
import app.models  # noqa: F401 - register SQLAlchemy models


logger = logging.getLogger(__name__)


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
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
register_exception_handlers(app)
from app.api.v1.router import router
app.include_router(router)


def custom_openapi() -> dict:
    """Expose multipart uploads as file inputs in Swagger UI."""

    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    operation = schema["paths"]["/api/batches/{batch_id}/documents"]["post"]
    request_schema = operation["requestBody"]["content"]["multipart/form-data"]["schema"]
    body_schema = schema["components"]["schemas"][request_schema["$ref"].rsplit("/", 1)[-1]]
    body_schema["properties"]["files"]["items"]["format"] = "binary"
    operation["summary"] = "Upload documents"
    operation["description"] = (
        "Upload one or more PDF/image files. In Swagger UI, use the file picker "
        "to select one or several files. Upload does not start LLM extraction."
    )
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    """Return a lightweight health status for monitoring."""

    return {"status": "ok", "environment": settings.app_env}
