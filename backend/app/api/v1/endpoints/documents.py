from io import BytesIO
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import require_roles
from app.db.session import get_db
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentResponse
from app.schemas.anomaly import (
    CorrectFieldsRequest,
    DocumentRejectRequest,
    DocumentReviewRequest,
    ResolveAnomalyRequest,
)
from app.services.extraction_service import ExtractionService
from app.storage.manager import StorageManager

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("/{document_id}/fields")
def list_fields(document_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    from app.models.extracted_field import ExtractedField
    document = db.scalar(select(Document).where(Document.public_id == document_id))
    if document is None:
        raise NotFoundError("Document not found")
    fields = db.query(ExtractedField).filter(ExtractedField.document_id == document.id).all()
    return [{"public_id": f.public_id, "field_name": f.field_name, "value": f.value, "corrected_value": f.corrected_value, "confidence": f.confidence, "status": f.status, "source_page": f.source_page, "source_text": f.source_text, "source_bbox": f.source_bbox} for f in fields]


@router.put("/{document_id}/fields")
def correct_fields(document_id: UUID, payload: CorrectFieldsRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "ACCOUNTANT"))):
    from datetime import datetime, UTC
    from app.models.audit_log import AuditLog
    from app.models.extracted_field import ExtractedField
    from app.validators.anomaly_detector import AnomalyDetector

    document = db.scalar(select(Document).where(Document.public_id == document_id))
    if document is None:
        raise NotFoundError("Document not found")
    if document.status == "READY":
        from app.models.invoice import Invoice

        if db.scalar(select(Invoice.id).where(Invoice.document_id == document.id)):
            raise ConflictError(
                "Fields cannot be corrected after an invoice draft has been created"
            )
        document.status = "REVIEW_REQUIRED"
        from app.models.audit_log import AuditLog

        db.add(AuditLog(
            user_id=user.id,
            action="DOCUMENT_REVIEW_INVALIDATED",
            entity_type="Document",
            entity_id=str(document.public_id),
            previous_value="READY",
            new_value="REVIEW_REQUIRED",
        ))
    corrections = payload.corrections
    for correction in corrections:
        field = db.query(ExtractedField).filter(
            ExtractedField.document_id == document.id,
            ExtractedField.field_name == correction.field_name,
        ).first()
        if field is None:
            raise NotFoundError(f"Extracted field not found: {correction.field_name}")
        old_value = field.corrected_value if field.corrected_value is not None else field.value
        field.corrected_value = correction.corrected_value
        field.corrected_by = user.id
        field.corrected_at = datetime.now(UTC)
        field.status = "CORRECTED"
        db.add(AuditLog(
            user_id=user.id,
            action="DOCUMENT_FIELD_CORRECTED",
            entity_type="ExtractedField",
            entity_id=str(field.public_id),
            previous_value=old_value,
            new_value=correction.corrected_value,
        ))
    AnomalyDetector().detect(db, document, commit=False, actor_id=user.id)
    db.commit()
    return {"status": "corrected", "count": len(corrections)}


@router.get("/{document_id}/anomalies")
def get_anomalies(document_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    from app.models.anomaly import Anomaly
    document = db.scalar(select(Document).where(Document.public_id == document_id))
    if document is None:
        raise NotFoundError("Document not found")
    anomalies = db.query(Anomaly).filter(Anomaly.document_id == document.id).all()
    return [{"public_id": anomaly.public_id, "field_name": anomaly.field_name, "anomaly_type": anomaly.anomaly_type, "severity": anomaly.severity, "description": anomaly.description, "expected_value": anomaly.expected_value, "actual_value": anomaly.actual_value, "status": anomaly.status} for anomaly in anomalies]


@router.post("/{document_id}/anomalies/{anomaly_id}/resolve")
def resolve_blocker(
    document_id: UUID,
    anomaly_id: UUID,
    payload: ResolveAnomalyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "ACCOUNTANT")),
):
    from datetime import UTC, datetime

    from app.models.anomaly import Anomaly
    from app.models.audit_log import AuditLog
    from app.models.extracted_field import ExtractedField
    from app.validators.anomaly_detector import AnomalyDetector

    document = db.scalar(select(Document).where(Document.public_id == document_id))
    if document is None:
        raise NotFoundError("Document not found")
    anomaly = db.query(Anomaly).filter(
        Anomaly.public_id == anomaly_id,
        Anomaly.document_id == document.id,
        Anomaly.status == "OPEN",
        Anomaly.severity == "BLOCKER",
    ).first()
    if anomaly is None:
        raise NotFoundError("Open blocker anomaly not found")
    field = db.query(ExtractedField).filter(
        ExtractedField.document_id == document.id,
        ExtractedField.field_name == payload.field_name,
    ).first()
    if field is None:
        raise NotFoundError(f"Extracted field not found: {payload.field_name}")
    prior = field.corrected_value if field.corrected_value is not None else field.value
    field.corrected_value = payload.corrected_value
    field.corrected_by = user.id
    field.corrected_at = datetime.now(UTC)
    field.status = "CORRECTED"
    anomalies = AnomalyDetector().detect(db, document, commit=False, actor_id=user.id)
    if any(
        item.severity == "BLOCKER"
        and item.anomaly_type == anomaly.anomaly_type
        and item.field_name == anomaly.field_name
        for item in anomalies
    ):
        db.rollback()
        raise ConflictError("The correction does not resolve this blocker")
    db.add(AuditLog(
        user_id=user.id,
        action="BLOCKER_RESOLVED",
        entity_type="Anomaly",
        entity_id=str(anomaly.public_id),
        previous_value=prior,
        new_value=f"{payload.corrected_value}; {payload.resolution_note}",
    ))
    db.commit()
    return {"status": "resolved", "anomaly_id": str(anomaly.public_id)}


@router.post("/{document_id}/review")
def review_document(document_id: UUID, payload: DocumentReviewRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    from datetime import UTC, datetime

    from app.models.anomaly import Anomaly
    from app.models.audit_log import AuditLog

    document = db.scalar(select(Document).where(Document.public_id == document_id))
    if document is None:
        raise NotFoundError("Document not found")
    if document.status not in {"REVIEW_REQUIRED", "EXTRACTED"}:
        raise ConflictError("Document must be extracted before review")
    blocker = db.query(Anomaly).filter(
        Anomaly.document_id == document.id,
        Anomaly.severity == "BLOCKER",
        Anomaly.status == "OPEN",
    ).first()
    if blocker:
        raise ConflictError("A blocker anomaly must be resolved before review")
    if not payload.confirmed:
        raise ConflictError("Review requires explicit confirmation")
    open_warnings = db.query(Anomaly).filter(
        Anomaly.document_id == document.id,
        Anomaly.severity == "WARNING",
        Anomaly.status == "OPEN",
    ).all()
    warning_decision = payload.warning_decision
    if open_warnings and not warning_decision:
        raise ConflictError("A decision is required for open warning anomalies")
    for anomaly in open_warnings:
        anomaly.status = "RESOLVED"
        anomaly.resolved_by = user.id
        anomaly.resolved_at = datetime.now(UTC)
    previous_status = document.status
    document.status = "READY"
    db.add(AuditLog(
        user_id=user.id,
        action="DOCUMENT_REVIEWED",
        entity_type="Document",
        entity_id=str(document.public_id),
        previous_value=previous_status,
        new_value=warning_decision or "No warnings",
    ))
    db.commit()
    return {"status": "READY", "reviewed_by": user.id}


@router.post("/{document_id}/reject")
def reject_document(document_id: UUID, payload: DocumentRejectRequest, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    from app.models.audit_log import AuditLog

    document = db.scalar(select(Document).where(Document.public_id == document_id))
    if document is None:
        raise NotFoundError("Document not found")
    previous_status = document.status
    document.status = "REJECTED"
    document.error_message = payload.reason or "Rejected during human review"
    db.add(AuditLog(
        user_id=user.id,
        action="DOCUMENT_REJECTED",
        entity_type="Document",
        entity_id=str(document.public_id),
        previous_value=previous_status,
        new_value=document.error_message,
    ))
    db.commit()
    return {"status": "REJECTED", "rejected_by": user.id}


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    document = db.scalar(select(Document).where(Document.public_id == document_id))
    if document is None:
        raise NotFoundError("Document not found")
    return document


@router.get("/{document_id}/preview")
def preview_document(document_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT", "VALIDATOR"))):
    document = db.scalar(select(Document).where(Document.public_id == document_id))
    if document is None:
        raise NotFoundError("Document not found")
    content = StorageManager().read(document.storage_backend, document.storage_key, document.sha256)
    filename = quote(document.original_filename, safe="")
    return StreamingResponse(
        BytesIO(content),
        media_type=document.mime_type,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{filename}"},
    )


@router.post("/{document_id}/extract")
def extract_document(document_id: UUID, db: Session = Depends(get_db), _user: User = Depends(require_roles("ADMIN", "ACCOUNTANT"))):
    document = db.scalar(select(Document).where(Document.public_id == document_id))
    if document is None:
        raise NotFoundError("Document not found")
    content = StorageManager().read(document.storage_backend, document.storage_key, document.sha256)
    try:
        return ExtractionService().extract(db, document, content, actor_id=_user.id)
    except RuntimeError as exc:
        raise ConflictError(str(exc)) from exc
