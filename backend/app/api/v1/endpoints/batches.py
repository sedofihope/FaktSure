import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, UploadFile, File
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_roles
from app.db.session import get_db
from app.models.document_batch import DocumentBatch
from app.models.user import User
from app.schemas.batch import BatchCreate, BatchResponse

router = APIRouter(tags=["batches"])
logger = logging.getLogger(__name__)


@router.post("/batches/{batch_id}/documents")
async def upload_documents(batch_id: UUID, files: list[UploadFile] = File(...), db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT"))):
    """Import files individually, preserving originals and reporting each result."""

    batch = db.scalar(select(DocumentBatch).where(DocumentBatch.public_id == batch_id))
    if batch is None:
        raise NotFoundError("Batch not found")

    from app.extractors.detector import classify_document
    from app.storage.manager import StorageManager
    from app.utils.hashing import sha256_bytes
    from app.models.document import Document
    from app.core.runtime_settings import get_runtime_settings
    from app.models.audit_log import AuditLog

    allowed_types = {"application/pdf", "image/png", "image/jpeg", "image/tiff", "image/webp", "application/octet-stream"}
    storage = StorageManager()
    max_file_size = get_runtime_settings().max_upload_size_mb * 1024 * 1024
    results = []
    for file in files:
        try:
            content = await file.read()
            if not content:
                raise ValueError("Empty file")
            if len(content) > max_file_size:
                raise ValueError(f"File exceeds {get_runtime_settings().max_upload_size_mb} MB")
            declared_mime = file.content_type or "application/octet-stream"
            if declared_mime not in allowed_types:
                raise ValueError("MIME type is not supported")
            detected_mime = _detect_mime_type(content)
            if detected_mime is None:
                raise ValueError("File signature is not a supported PDF or image")
            if declared_mime not in {detected_mime, "application/octet-stream"}:
                logger.info("Upload MIME type did not match file signature; using detected type")
            digest = sha256_bytes(content)
            existing = db.query(Document).filter(Document.sha256 == digest).first()
            if existing:
                results.append({"filename": file.filename, "status": "duplicate", "document_id": str(existing.public_id), "sha256": digest, "error": "Identical document already exists"})
                continue
            document_type, confidence, engine = classify_document(content, file.filename or "", detected_mime)
            key = f"{batch.id}/{digest}"
            backend, local_path = storage.save(key, content)
            document = Document(batch_id=batch.id, original_filename=file.filename or "document", mime_type=detected_mime, file_size=len(content), document_type=document_type, classification_confidence=confidence, processing_engine=engine, storage_backend=backend, storage_key=key, local_path=local_path, sha256=digest, status="UPLOADED" if document_type == "NATIVE_PDF" else "FAILED", error_message=None if document_type == "NATIVE_PDF" else "Extraction engine unavailable for this document type")
            db.add(document); db.commit(); db.refresh(document)
            batch.total_documents += 1
            if document.status == "FAILED":
                batch.failed_documents += 1
            db.add(AuditLog(
                user_id=_user.id,
                action="DOCUMENT_IMPORTED",
                entity_type="Document",
                entity_id=str(document.public_id),
                new_value=f"sha256={digest};type={document_type}",
            ))
            db.commit()
            results.append({"filename": file.filename, "status": "uploaded", "document_id": str(document.public_id), "sha256": digest, "error": None})
        except Exception as exc:
            db.rollback()
            if isinstance(exc, ValueError):
                message = str(exc)
            else:
                logger.error("Document upload failed (%s)", type(exc).__name__)
                message = f"File import failed: {type(exc).__name__}"
            results.append({"filename": file.filename, "status": "error", "document_id": None, "sha256": None, "error": message})
    db.commit()
    return {"batch_id": str(batch.public_id), "results": results}


def _detect_mime_type(content: bytes) -> str | None:
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    return None


@router.post("/batches/{batch_id}/process", status_code=202)
def process_batch(
    batch_id: UUID,
    background_tasks: BackgroundTasks,
    retry_failed: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT")),
):
    """Queue native PDFs for sequential background extraction and validation."""

    batch = db.scalar(select(DocumentBatch).where(DocumentBatch.public_id == batch_id))
    if batch is None:
        raise NotFoundError("Batch not found")
    if batch.status == "PROCESSING":
        raise ConflictError("Batch is already being processed")

    from app.models.document import Document

    eligible_statuses = ["QUEUED", "UPLOADED"]
    if retry_failed:
        eligible_statuses.append("FAILED")
    eligible = db.query(Document).filter(
        Document.batch_id == batch.id,
        Document.document_type == "NATIVE_PDF",
        Document.status.in_(eligible_statuses),
    ).all()
    if not eligible:
        raise ConflictError("No eligible native PDF documents to process")
    for document in eligible:
        document.status = "QUEUED"
        document.error_message = None

    changed = db.execute(
        update(DocumentBatch)
        .where(DocumentBatch.id == batch.id, DocumentBatch.status != "PROCESSING")
        .values(status="PROCESSING")
    )
    if changed.rowcount != 1:
        db.rollback()
        raise ConflictError("Batch is already being processed")
    db.commit()

    from app.services.batch_service import process_batch_in_background

    background_tasks.add_task(process_batch_in_background, batch.id)
    return {"batch_id": str(batch.public_id), "status": "PROCESSING", "queued_documents": len(eligible)}


@router.post("/batches", response_model=BatchResponse, status_code=201)
def create_batch(payload: BatchCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "ACCOUNTANT"))):
    from app.models.audit_log import AuditLog

    batch = DocumentBatch(name=payload.name, created_by=user.id)
    db.add(batch)
    db.flush()
    db.add(AuditLog(
        user_id=user.id,
        action="BATCH_CREATED",
        entity_type="DocumentBatch",
        entity_id=str(batch.public_id),
    ))
    db.commit(); db.refresh(batch)
    return batch

@router.get("/batches", response_model=list[BatchResponse])
def list_batches(db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    return list(db.scalars(select(DocumentBatch).order_by(DocumentBatch.id.desc())))

@router.get("/batches/{batch_id}", response_model=BatchResponse)
def get_batch(batch_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    batch = db.scalar(select(DocumentBatch).where(DocumentBatch.public_id == batch_id))
    if batch is None:
        raise NotFoundError("Batch not found")
    return batch
