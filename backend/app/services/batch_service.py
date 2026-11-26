import logging
import asyncio
import threading

from sqlalchemy import func, select

from app.core.runtime_settings import get_runtime_settings
from app.db.session import SessionLocal
from app.models.document import Document
from app.models.document_batch import DocumentBatch
from app.services.extraction_service import ExtractionService
from app.storage.manager import StorageManager

logger = logging.getLogger(__name__)
_batch_locks_guard = threading.Lock()
_batch_locks: dict[int, threading.Lock] = {}
_worker_condition = threading.Condition()
_active_batch_workers = 0


def process_batch_in_background(batch_id: int) -> None:
    """Run one batch under the configured process-wide concurrency limit."""

    global _active_batch_workers
    with _batch_locks_guard:
        batch_lock = _batch_locks.setdefault(batch_id, threading.Lock())
    with batch_lock:
        with _worker_condition:
            while _active_batch_workers >= max(
                get_runtime_settings().max_document_concurrency,
                1,
            ):
                _worker_condition.wait()
            _active_batch_workers += 1
        try:
            _process_batch(batch_id)
        finally:
            with _worker_condition:
                _active_batch_workers -= 1
                _worker_condition.notify_all()


async def resume_queued_batches(batch_ids: list[int]) -> None:
    """Resume explicitly queued batches sequentially after application startup."""

    for batch_id in batch_ids:
        await asyncio.to_thread(process_batch_in_background, batch_id)


def recover_interrupted_batches() -> list[int]:
    """Return queued batches and make interrupted extraction states retryable."""

    db = SessionLocal()
    try:
        interrupted = db.scalars(
            select(Document).where(Document.status == "EXTRACTING")
        ).all()
        for document in interrupted:
            document.status = "QUEUED"
            document.error_message = None

        processing_batches = db.scalars(
            select(DocumentBatch).where(DocumentBatch.status == "PROCESSING")
        ).all()
        queued_batch_ids: set[int] = set()
        for batch in processing_batches:
            queued = db.scalar(
                select(Document.id).where(
                    Document.batch_id == batch.id,
                    Document.status.in_(["QUEUED", "EXTRACTING"]),
                ).limit(1)
            )
            if queued is not None:
                queued_batch_ids.add(batch.id)
                continue
            batch.processed_documents = db.scalar(
                select(func.count(Document.id)).where(
                    Document.batch_id == batch.id,
                    Document.status.in_(["REVIEW_REQUIRED", "READY", "REJECTED"]),
                )
            ) or 0
            batch.failed_documents = db.scalar(
                select(func.count(Document.id)).where(
                    Document.batch_id == batch.id,
                    Document.status == "FAILED",
                )
            ) or 0
            batch.status = "PARTIALLY_COMPLETED" if batch.failed_documents else "COMPLETED"

        queued_batch_ids.update(db.scalars(
            select(Document.batch_id)
            .where(Document.status == "QUEUED")
            .distinct()
        ).all())
        db.commit()
        return sorted(queued_batch_ids)
    finally:
        db.close()


def _process_batch(batch_id: int) -> None:
    """Extract queued native PDFs sequentially and persist each result."""

    db = SessionLocal()
    try:
        batch = db.get(DocumentBatch, batch_id)
        if batch is None:
            logger.error("Queued batch %s no longer exists", batch_id)
            return

        settings = get_runtime_settings()
        document_ids = list(
            db.scalars(
                select(Document.id)
                .where(Document.batch_id == batch_id, Document.status == "QUEUED")
                .order_by(Document.id)
            )
        )
        batch_size = max(settings.document_batch_size, 1)
        storage = StorageManager()
        for start in range(0, len(document_ids), batch_size):
            for document_id in document_ids[start : start + batch_size]:
                document = db.get(Document, document_id)
                if document is None:
                    continue
                try:
                    content = storage.read(
                        document.storage_backend,
                        document.storage_key,
                        document.sha256,
                    )
                    ExtractionService().extract(
                        db,
                        document,
                        content,
                        actor_id=batch.created_by,
                    )
                except Exception as exc:
                    db.rollback()
                    document = db.get(Document, document_id)
                    if document is not None:
                        document.status = "FAILED"
                        document.error_message = f"Processing failed: {type(exc).__name__}"
                        db.commit()
                    logger.error(
                        "Document %s failed during batch processing (%s)",
                        document_id,
                        type(exc).__name__,
                    )

        batch = db.get(DocumentBatch, batch_id)
        if batch is not None:
            remaining = db.scalar(
                select(Document.id)
                .where(
                    Document.batch_id == batch_id,
                    Document.status.in_(["QUEUED", "EXTRACTING"]),
                )
                .limit(1)
            )
            batch.processed_documents = db.scalar(
                select(func.count(Document.id)).where(
                    Document.batch_id == batch_id,
                    Document.status.in_(["REVIEW_REQUIRED", "READY", "REJECTED"]),
                )
            ) or 0
            batch.failed_documents = db.scalar(
                select(func.count(Document.id)).where(
                    Document.batch_id == batch_id,
                    Document.status == "FAILED",
                )
            ) or 0
            batch.status = "PROCESSING" if remaining else (
                "PARTIALLY_COMPLETED" if batch.failed_documents else "COMPLETED"
            )
            db.commit()
    finally:
        db.close()