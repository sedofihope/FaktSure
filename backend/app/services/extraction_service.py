import json
import logging

from sqlalchemy.orm import Session

from app.ai.factory import get_llm_provider
from app.extractors.native_pdf import extract_native_pdf
from app.models.document import Document
from app.models.extracted_field import ExtractedField
from app.models.audit_log import AuditLog
from app.schemas.extraction import ExtractionResponse

logger = logging.getLogger(__name__)


class ExtractionService:
    """Extract and persist a native PDF using an interchangeable LLM provider."""

    def extract(
        self,
        db: Session,
        document: Document,
        content: bytes,
        actor_id: int | None = None,
    ) -> ExtractionResponse:
        if document.document_type != "NATIVE_PDF":
            document.status = "FAILED"
            document.error_message = f"Extraction unavailable for {document.document_type}"
            db.add(AuditLog(
                user_id=actor_id,
                action="DOCUMENT_EXTRACTION_FAILED",
                entity_type="Document",
                entity_id=str(document.public_id),
                new_value=document.error_message,
            ))
            db.commit()
            raise RuntimeError(document.error_message)
        if document.status not in {"UPLOADED", "QUEUED", "FAILED"}:
            raise RuntimeError(f"Document cannot be extracted from status {document.status}")

        document.status = "EXTRACTING"
        db.commit()
        try:
            pages = extract_native_pdf(content)
            text = "\n".join(f"[PAGE {p['page']}]\n{p['text']}" for p in pages)
            data = get_llm_provider().extract_structured(text)
            extracted = ExtractionResponse.model_validate(data)
        except Exception as exc:
            logger.error("Document extraction failed (%s)", type(exc).__name__)
            document.status = "FAILED"
            document.error_message = f"Extraction failed: {type(exc).__name__}"
            db.add(AuditLog(
                user_id=actor_id,
                action="DOCUMENT_EXTRACTION_FAILED",
                entity_type="Document",
                entity_id=str(document.public_id),
                new_value=document.error_message,
            ))
            db.commit()
            raise RuntimeError(document.error_message) from None

        for field_name, value in extracted.model_dump(exclude={"items"}).items():
            source_page, source_text, source_bbox = self._find_source(pages, value)
            confidence = 0.85 if value is not None and source_text else 0.35 if value is not None else 0.0
            db.add(ExtractedField(
                document_id=document.id,
                field_name=field_name,
                value=None if value is None else str(value),
                confidence=confidence,
                status="MISSING" if value is None else "RELIABLE" if source_text else "UNCERTAIN",
                source_page=source_page,
                source_text=source_text,
                source_bbox=source_bbox,
            ))
        for index, item in enumerate(extracted.items):
            source_page, source_text, source_bbox = self._find_source(pages, item.description)
            confidence = min(item.confidence, 0.85) if source_text else min(item.confidence, 0.35)
            db.add(ExtractedField(
                document_id=document.id,
                field_name=f"item.{index}",
                value=item.model_dump_json(),
                confidence=confidence,
                status="RELIABLE" if source_text and confidence >= 0.6 else "UNCERTAIN",
                source_page=source_page,
                source_text=source_text,
                source_bbox=source_bbox,
            ))
        document.status = "REVIEW_REQUIRED"
        document.processing_engine = "py-mupdf + configured-llm"
        db.add(AuditLog(
            user_id=actor_id,
            action="DOCUMENT_EXTRACTED",
            entity_type="Document",
            entity_id=str(document.public_id),
            new_value=f"fields={len(extracted.model_dump(exclude={'items'}))}; items={len(extracted.items)}",
        ))
        db.commit()
        from app.validators.anomaly_detector import AnomalyDetector

        AnomalyDetector().detect(db, document, actor_id=actor_id)
        return extracted

    @staticmethod
    def _find_source(pages: list[dict], value: object) -> tuple[int | None, str | None, str | None]:
        """Find exact extracted text in PDF blocks; never infer coordinates."""

        if value is None:
            return None, None, None
        needle = " ".join(str(value).casefold().split())
        if not needle:
            return None, None, None
        for page in pages:
            for block in page["blocks"]:
                block_text = " ".join(block["text"].casefold().split())
                if needle in block_text:
                    return page["page"], block["text"], json.dumps(block["bbox"])
        return None, None, None
