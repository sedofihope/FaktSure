from decimal import Decimal
from datetime import date
from io import BytesIO
from uuid import UUID

import pymupdf
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.models.tax_rule import TaxRule


def test_document_to_validated_invoice_workflow(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_db():
        with test_sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db

    with test_sessions() as db:
        db.add(User(
            full_name="Workflow Admin",
            email="workflow@example.com",
            password_hash=hash_password("workflow-test-password"),
            role="ADMIN",
        ))
        db.add(TaxRule(
            name="TVA 18%",
            rate=Decimal("18"),
            calculation_type="PERCENTAGE",
            valid_from=date(2020, 1, 1),
            is_active=True,
        ))
        db.commit()

    class FakeStorage:
        objects = {}

        def save(self, key, payload):
            self.objects[key] = payload
            return "local", f"/tmp/{key}"

        def save_essential(self, key, payload):
            self.objects[key] = payload
            return "r2", ""

        def read(self, backend, key, digest):
            return self.objects[key]

    class FakeProvider:
        def extract_structured(self, text):
            assert "INV-2026-001" in text
            return {
                "document_type": "INVOICE",
                "document_number": "INV-2026-001",
                "document_date": "2026-11-25",
                "due_date": "2026-12-25",
                "currency": "FCFA",
                "client_name": "Client Démo",
                "client_address": "Agla, parcelle fictive 99\nOuidah",
                "client_tax_identifier": "IFU-FICTIF-47294055",
                "client_rccm": "SN-DKR-2026-B-00001",
                "client_phone": "+229 01 56 81 51 88",
                "client_email": "contact309@exemple.bj",
                "subtotal": "381000",
                "discount_total": "38100",
                "tax_total": "61722",
                "grand_total": "404622",
                "items": [
                    {
                        "description": "Carreau grès cérame",
                        "quantity": "8",
                        "unit": "carton",
                        "unit_price": "13125",
                        "discount": None,
                        "line_total": "105000",
                        "confidence": 0.95,
                    },
                    {
                        "description": "Ciment CPJ 35",
                        "quantity": "5",
                        "unit": "sac",
                        "unit_price": "5040",
                        "discount": None,
                        "line_total": "25200",
                        "confidence": 0.95,
                    },
                    {
                        "description": "Peinture acrylique",
                        "quantity": "8",
                        "unit": "pot",
                        "unit_price": "31350",
                        "discount": None,
                        "line_total": "250800",
                        "confidence": 0.95,
                    },
                ],
            }

    monkeypatch.setattr("app.storage.manager.StorageManager", FakeStorage)
    monkeypatch.setattr(
        "app.api.v1.endpoints.invoices.StorageManager",
        FakeStorage,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.documents.StorageManager",
        FakeStorage,
    )
    monkeypatch.setattr(
        "app.services.extraction_service.get_llm_provider",
        lambda: FakeProvider(),
    )
    FakeStorage.objects.clear()

    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/auth/login",
                json={
                    "email": "workflow@example.com",
                    "password": "workflow-test-password",
                },
            )
            assert login.status_code == 200
            headers = {
                "Authorization": f"Bearer {login.json()['access_token']}",
            }

            client_response = client.post(
                "/api/clients",
                headers=headers,
                json={
                    "name": "Client Démo",
                    "rccm": "SN-DKR-2026-B-00001",
                },
            )
            assert client_response.status_code == 201
            assert client_response.json()["rccm"] == "SN-DKR-2026-B-00001"
            client_id = UUID(client_response.json()["public_id"])

            batch_response = client.post(
                "/api/batches",
                headers=headers,
                json={"name": "E2E invoice workflow"},
            )
            assert batch_response.status_code == 201
            batch_id = UUID(batch_response.json()["public_id"])

            pdf = pymupdf.open()
            page = pdf.new_page()
            page.insert_text(
                (50, 50),
                "INVOICE INV-2026-001 2026-11-25 2026-12-25 "
                "XOF Client Démo Service conseil 1 100.00",
            )
            content = pdf.tobytes()
            pdf.close()

            upload_response = client.post(
                f"/api/batches/{batch_id}/documents",
                headers=headers,
                files=[("files", ("invoice.pdf", BytesIO(content), "application/pdf"))],
            )
            assert upload_response.status_code == 200
            upload = upload_response.json()["results"][0]
            assert upload["status"] == "uploaded"
            document_id = UUID(upload["document_id"])

            document_response = client.get(
                f"/api/documents/{document_id}",
                headers=headers,
            )
            assert document_response.status_code == 200
            assert document_response.json()["batch_id"] == str(batch_id)

            extraction_response = client.post(
                f"/api/documents/{document_id}/extract",
                headers=headers,
            )
            assert extraction_response.status_code == 200
            assert extraction_response.json()["document_number"] == "INV-2026-001"

            fields_response = client.get(
                f"/api/documents/{document_id}/fields",
                headers=headers,
            )
            assert fields_response.status_code == 200
            fields = fields_response.json()
            assert fields
            assert all(UUID(field["public_id"]) for field in fields)
            assert next(
                field["value"] for field in fields
                if field["field_name"] == "client_rccm"
            ) == "SN-DKR-2026-B-00001"

            anomalies_response = client.get(
                f"/api/documents/{document_id}/anomalies",
                headers=headers,
            )
            assert anomalies_response.status_code == 200
            assert not any(
                item["severity"] == "BLOCKER" and item["status"] == "OPEN"
                for item in anomalies_response.json()
            )

            review_response = client.post(
                f"/api/documents/{document_id}/review",
                headers=headers,
                json={"confirmed": True, "warning_decision": "Accepted"},
            )
            assert review_response.status_code == 200
            assert review_response.json()["status"] == "READY"

            rejected_payload = client.post(
                f"/api/documents/{document_id}/reject",
                headers=headers,
                json={"unexpected": "not accepted"},
            )
            assert rejected_payload.status_code == 422

            invoice_response = client.post(
                "/api/invoices",
                headers=headers,
                json={"document_id": str(document_id)},
            )
            assert invoice_response.status_code == 201
            draft = invoice_response.json()
            invoice_id = UUID(draft["public_id"])
            assert draft["document_id"] == str(document_id)
            assert draft["client_id"] == str(client_id)
            assert draft["status"] == "DRAFT"
            assert draft["issue_date"] == date.today().isoformat()
            assert draft["due_date"] is None
            assert draft["currency"] == "XOF"
            assert draft["currency"] == "XOF"
            assert draft["subtotal"] == "381000"
            assert draft["discount_total"] == "38100"
            assert draft["tax_total"] == "61722"
            assert draft["grand_total"] == "404622"
            assert Decimal(draft["subtotal"]) == Decimal("381000.00")
            assert Decimal(draft["discount_total"]) == Decimal("38100.00")
            assert Decimal(draft["tax_total"]) == Decimal("61722.00")
            assert Decimal(draft["grand_total"]) == Decimal("404622.00")
            from app.models import InvoiceItem

            with test_sessions() as db:
                invoice_items = db.query(InvoiceItem).order_by(InvoiceItem.id).all()
                assert len(invoice_items) == 3
                assert sum(
                    (item.discount for item in invoice_items),
                    Decimal("0"),
                ) == Decimal("38100.000000")
                assert sum(
                    (item.line_total for item in invoice_items),
                    Decimal("0"),
                ) == Decimal("342900.000000")
                assert [item.unit_price for item in invoice_items] == [
                    Decimal("13125.000000"),
                    Decimal("5040.000000"),
                    Decimal("31350.000000"),
                ]

            draft_pdf_response = client.get(
                f"/api/invoices/{invoice_id}/pdf",
                headers=headers,
            )
            assert draft_pdf_response.status_code == 200
            draft_pdf = pymupdf.open(
                stream=draft_pdf_response.content,
                filetype="pdf",
            )
            draft_pdf_text = "\n".join(
                page.get_text() for page in draft_pdf
            )
            draft_pdf.close()
            assert "BROUILLON" in draft_pdf_text
            assert "NON ÉMISE" in draft_pdf_text
            assert "Référence provisoire" in draft_pdf_text
            assert "IFU · IFU-FICTIF-47294055" in draft_pdf_text
            assert "SN-DKR-2026-B-00001" in draft_pdf_text
            assert "Agla, parcelle fictive 99" in draft_pdf_text
            assert "contact309@exemple.bj" in draft_pdf_text
            assert "01 56 81 51 88" in draft_pdf_text
            assert "13 125" in draft_pdf_text
            assert "10 %" in draft_pdf_text
            assert "TVA" in draft_pdf_text
            assert "18 %" in draft_pdf_text
            assert "Base soumise à TVA" in draft_pdf_text
            assert "342 900" in draft_pdf_text

            validation_response = client.post(
                f"/api/invoices/{invoice_id}/validate",
                headers=headers,
            )
            assert validation_response.status_code == 200
            issued = validation_response.json()
            assert issued["public_id"] == str(invoice_id)
            assert issued["invoice_number"].startswith("FS-2026-")
            assert issued["status"] == "ISSUED"
            with test_sessions() as db:
                from app.models import Invoice

                persisted_invoice = db.query(Invoice).one()
                assert persisted_invoice.pdf_format_version == 8
                persisted_invoice.pdf_format_version = None

            persisted_response = client.get(
                f"/api/invoices/{invoice_id}",
                headers=headers,
            )
            assert persisted_response.status_code == 200
            assert persisted_response.json()["status"] == "ISSUED"

            pdf_response = client.get(
                f"/api/invoices/{invoice_id}/pdf",
                headers=headers,
            )
            assert pdf_response.status_code == 200
            assert pdf_response.headers["content-type"] == "application/pdf"
            assert pdf_response.headers["content-disposition"].startswith("attachment;")
            assert pdf_response.content.startswith(b"%PDF-")
            pdf_document = pymupdf.open(stream=pdf_response.content, filetype="pdf")
            pdf_text = "\n".join(page.get_text() for page in pdf_document)
            pdf_document.close()
            assert "FS-2026-000001" in pdf_text
            assert "BROUILLON" not in pdf_text
            assert "Carreau grès cérame" in pdf_text
            assert "carton" in pdf_text
            assert "13 125" in pdf_text
            assert "10 500" in pdf_text
            assert "94 500" in pdf_text
            assert "225 720" in pdf_text
            assert "Total HT" in pdf_text
            assert "381 000 FCFA (XOF)" in pdf_text
            assert "Remises" in pdf_text
            assert "38 100 FCFA (XOF)" in pdf_text
            assert "61 722 FCFA (XOF)" in pdf_text
            assert "404 622 FCFA (XOF)" in pdf_text
            assert ".000000" not in pdf_text
            with test_sessions() as db:
                from app.models import Invoice

                persisted_invoice = db.query(Invoice).one()
                assert persisted_invoice.pdf_storage_backend == "r2"
                assert persisted_invoice.pdf_format_version == 8
                assert persisted_invoice.pdf_storage_key == (
                    f"invoices/{invoice_id}/invoice.pdf"
                )
                assert len(persisted_invoice.pdf_sha256) == 64
                stored_pdf = FakeStorage.objects[persisted_invoice.pdf_storage_key]
            assert pdf_response.content == stored_pdf

            repeated_pdf_response = client.get(
                f"/api/invoices/{invoice_id}/pdf",
                headers=headers,
            )
            assert repeated_pdf_response.status_code == 200
            assert repeated_pdf_response.content == pdf_response.content
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(engine)
        engine.dispose()
