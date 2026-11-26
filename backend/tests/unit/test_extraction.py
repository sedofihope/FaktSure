from datetime import date
from decimal import Decimal

import pytest
import pymupdf
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Client, Document, DocumentBatch, ExtractedField, User
from app.schemas.extraction import ExtractionResponse
from app.services import extraction_service
from app.services.extraction_service import ExtractionService


def test_extraction_schema_accepts_missing_values_as_null():
    result = ExtractionResponse.model_validate({"document_number": None, "items": []})
    assert result.document_number is None
    assert result.items == []


def test_extraction_schema_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        ExtractionResponse.model_validate({"items": [{"confidence": 1.5}]})


def test_extraction_uses_mock_provider_and_persists_real_pdf_provenance(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text(
        (72, 72),
        "Order PO-42 Date 2026-11-25 XOF Test Client Service 10.00",
    )
    pdf_bytes = pdf.tobytes()
    pdf.close()

    extracted_data = {
        "document_type": "PURCHASE_ORDER",
        "document_number": "PO-42",
        "document_date": "2026-11-25",
        "currency": "XOF",
        "client_name": "Test Client",
        "items": [{
            "description": "Service",
            "sku": None,
            "quantity": 1,
            "unit": "unit",
            "unit_price": 10,
            "discount": 0,
            "line_total": 10,
            "confidence": 0.9,
        }],
        "subtotal": 10,
        "discount_total": 0,
        "tax_total": 0,
        "grand_total": 10,
    }

    class FakeProvider:
        def extract_structured(self, text):
            assert "[PAGE 1]" in text
            return extracted_data

    monkeypatch.setattr(extraction_service, "get_llm_provider", lambda: FakeProvider())
    try:
        with sessions() as db:
            user = User(
                full_name="Tester",
                email="extraction@example.com",
                password_hash="unused",
                role="ACCOUNTANT",
            )
            db.add(user)
            db.flush()
            db.add(Client(name="Test Client"))
            batch = DocumentBatch(name="Batch", created_by=user.id)
            db.add(batch)
            db.flush()
            document = Document(
                batch_id=batch.id,
                original_filename="order.pdf",
                mime_type="application/pdf",
                file_size=len(pdf_bytes),
                document_type="NATIVE_PDF",
                storage_key="batch/doc",
                sha256="test-digest",
                status="QUEUED",
            )
            db.add(document)
            db.commit()

            result = ExtractionService().extract(db, document, pdf_bytes)

            client_name = db.query(ExtractedField).filter_by(
                document_id=document.id,
                field_name="client_name",
            ).one()
            item = db.query(ExtractedField).filter_by(
                document_id=document.id,
                field_name="item.0",
            ).one()
            assert result.document_number == "PO-42"
            assert document.status == "REVIEW_REQUIRED"
            assert client_name.source_page == 1
            assert client_name.source_text is not None
            assert client_name.source_bbox is not None
            assert item.source_page == 1
            assert item.status == "RELIABLE"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
