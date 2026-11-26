from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlparse

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Client, Document, DocumentBatch, ExtractedField, Invoice, InvoiceItem, InvoiceSequence, TaxRule, User
from app.schemas.invoice import InvoiceCreate, InvoiceItemCreate
from app.services.invoice_service import InvoiceService


@pytest.fixture
def invoice_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        user = User(
            full_name="Validator",
            email="validator@example.com",
            password_hash="unused",
            role="VALIDATOR",
        )
        db.add(user)
        db.flush()
        client = Client(name="Valid Client")
        db.add(client)
        db.flush()
        db.add(TaxRule(
            name="TVA 18%",
            rate=Decimal("18"),
            calculation_type="PERCENTAGE",
            valid_from=date(2020, 1, 1),
            is_active=True,
        ))
        batches = []
        for index in range(2):
            batch = DocumentBatch(name=f"Batch {index}", created_by=user.id)
            db.add(batch)
            db.flush()
            doc = Document(
                batch_id=batch.id,
                original_filename=f"doc-{index}.pdf",
                mime_type="application/pdf",
                file_size=4,
                document_type="NATIVE_PDF",
                storage_key=f"doc-{index}",
                sha256=f"sha-{index}",
                status="READY",
            )
            db.add(doc)
            db.flush()
            batches.append((doc.public_id, client.public_id))
        db.commit()
        yield db, user.id, batches
    Base.metadata.drop_all(engine)
    engine.dispose()


def make_invoice(document_id, client_id):
    return InvoiceCreate(
        document_id=document_id,
        client_id=client_id,
        issue_date=date(2026, 11, 25),
        currency="XOF",
        items=[
            InvoiceItemCreate(
                description="Work",
                quantity=Decimal("2"),
                unit_price=Decimal("10.125"),
                discount=Decimal("1"),
            )
        ],
    )


def test_invoice_sequence_is_atomic_and_validation_is_one_time(invoice_db, monkeypatch):
    db, validator_id, document_info = invoice_db
    service = InvoiceService()
    first = service.create_draft(db, make_invoice(*document_info[0]))
    second = service.create_draft(db, make_invoice(*document_info[1]))

    class FakeStorage:
        def save_essential(self, key, content):
            return "r2", ""

    monkeypatch.setattr("app.storage.manager.StorageManager", FakeStorage)
    service.validate(db, first, validator_id)
    service.validate(db, second, validator_id)

    assert first.invoice_number == "FS-2026-000001"
    assert second.invoice_number == "FS-2026-000002"
    assert first.status == "ISSUED"
    with pytest.raises(ValueError, match="not pending validation"):
        service.validate(db, first, validator_id)
    assert db.query(InvoiceSequence).filter_by(year=2026).one().next_number == 2
    assert first.pdf_storage_backend == "r2"
    assert first.pdf_sha256 is not None


def test_invoice_calculations_use_decimal_and_reject_invalid_discount(invoice_db):
    db, _validator_id, document_info = invoice_db
    service = InvoiceService()
    invoice = service.create_draft(db, make_invoice(*document_info[0]))

    assert invoice.subtotal == Decimal("20.25")
    assert invoice.discount_total == Decimal("1.00")
    assert invoice.tax_total == Decimal("0.00")
    assert invoice.grand_total == Decimal("19.25")
    assert db.query(InvoiceItem).filter_by(invoice_id=invoice.id).one().line_total == Decimal("19.25")

    invalid = make_invoice(*document_info[1])
    invalid.items[0].discount = Decimal("100")
    with pytest.raises(ValueError, match="discount cannot exceed"):
        service.create_draft(db, invalid)


def test_invoice_uses_default_issue_date_for_tax_rule_validation(invoice_db):
    db, _validator_id, document_info = invoice_db
    rule = db.query(TaxRule).one()
    payload = make_invoice(*document_info[0])
    payload.issue_date = None
    payload.items[0].tax_rule_id = rule.public_id

    invoice = InvoiceService().create_draft(db, payload)

    assert invoice.issue_date == date.today()
    assert invoice.tax_total == Decimal("3.47")
    assert invoice.grand_total == Decimal("22.72")


def test_invoice_level_vat_applies_to_net_total_after_discounts(invoice_db):
    db, _validator_id, document_info = invoice_db
    rule = db.query(TaxRule).one()
    payload = InvoiceCreate(
        document_id=document_info[0][0],
        client_id=document_info[0][1],
        issue_date=date(2026, 11, 25),
        currency="XOF",
        tax_rule_id=rule.public_id,
        items=[
            InvoiceItemCreate(
                description="Work",
                quantity=Decimal("1"),
                unit_price=Decimal("100"),
                discount=Decimal("10"),
            )
        ],
    )

    invoice = InvoiceService().create_draft(db, payload)

    assert invoice.tax_rule_id == rule.id
    assert invoice.subtotal == Decimal("100.00")
    assert invoice.discount_total == Decimal("10.00")
    assert invoice.tax_total == Decimal("16.20")
    assert invoice.grand_total == Decimal("106.20")
    assert db.query(InvoiceItem).filter_by(invoice_id=invoice.id).one().tax_rule_id is None


def test_invoice_rejects_combining_global_and_line_level_vat():
    with pytest.raises(ValidationError, match="not both"):
        InvoiceCreate(
            document_id="8c4a4b9e-4e51-46c1-8c4a-9b9f1d45a4c2",
            tax_rule_id="8c4a4b9e-4e51-46c1-8c4a-9b9f1d45a4c3",
            items=[
                InvoiceItemCreate(
                    description="Work",
                    quantity=Decimal("1"),
                    unit_price=Decimal("100"),
                    tax_rule_id="8c4a4b9e-4e51-46c1-8c4a-9b9f1d45a4c4",
                )
            ],
        )


def test_invoice_pdf_shows_global_vat_breakdown(invoice_db, monkeypatch):
    from app.services import invoice_pdf

    db, _validator_id, document_info = invoice_db
    rule = db.query(TaxRule).one()
    payload = InvoiceCreate(
        document_id=document_info[0][0],
        client_id=document_info[0][1],
        issue_date=date(2026, 11, 25),
        currency="XOF",
        tax_rule_id=rule.public_id,
        items=[
            InvoiceItemCreate(
                description="Work",
                quantity=Decimal("1"),
                unit_price=Decimal("100"),
                discount=Decimal("10"),
            )
        ],
    )
    invoice = InvoiceService().create_draft(db, payload)
    rendered_html = {}

    def fake_chromium(command, **_kwargs):
        html_path = Path(unquote(urlparse(command[-1]).path))
        rendered_html["content"] = html_path.read_text(encoding="utf-8")
        pdf_path = Path(command[command.index(next(
            argument for argument in command if argument.startswith("--print-to-pdf=")
        ))].split("=", 1)[1])
        pdf_path.write_bytes(b"%PDF-1.7\nfake")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(invoice_pdf.shutil, "which", lambda _name: "/usr/bin/chromium")
    monkeypatch.setattr(invoice_pdf.subprocess, "run", fake_chromium)

    assert invoice_pdf.render_invoice_pdf(db, invoice).startswith(b"%PDF-")
    assert "Base soumise à TVA 18% (18 %)" in rendered_html["content"]
    assert "90 FCFA (XOF)" in rendered_html["content"]


def test_invoice_is_not_issued_if_required_r2_storage_fails(invoice_db, monkeypatch):
    from app.core.exceptions import ServiceUnavailableError
    from app.storage.manager import R2StorageUnavailable

    db, validator_id, document_info = invoice_db
    invoice = InvoiceService().create_draft(db, make_invoice(*document_info[0]))

    class UnavailableStorage:
        def save_essential(self, _key, _content):
            raise R2StorageUnavailable("unavailable")

    monkeypatch.setattr("app.storage.manager.StorageManager", UnavailableStorage)
    with pytest.raises(ServiceUnavailableError, match="not issued"):
        InvoiceService().validate(db, invoice, validator_id)

    db.refresh(invoice)
    assert invoice.status == "DRAFT"
    assert invoice.pdf_storage_key is None


def test_invoice_draft_matches_client_by_exact_name_when_identifier_differs(invoice_db):
    db, _validator_id, document_info = invoice_db
    document_id, _client_id = document_info[0]
    document = db.scalar(select(Document).where(Document.public_id == document_id))
    db.add_all([
        ExtractedField(document_id=document.id, field_name="client_name", value="Valid Client", confidence=0.85, status="RELIABLE"),
        ExtractedField(document_id=document.id, field_name="client_tax_identifier", value="IFU-DIFFERENT", confidence=0.85, status="RELIABLE"),
        ExtractedField(document_id=document.id, field_name="currency", value="FCFA", confidence=0.85, status="RELIABLE"),
        ExtractedField(document_id=document.id, field_name="subtotal", value="381000", confidence=0.35, status="UNCERTAIN"),
        ExtractedField(document_id=document.id, field_name="discount_total", value="38100", confidence=0.35, status="UNCERTAIN"),
        ExtractedField(document_id=document.id, field_name="tax_total", value="61722", confidence=0.35, status="UNCERTAIN"),
        ExtractedField(document_id=document.id, field_name="grand_total", value="404622", confidence=0.35, status="UNCERTAIN"),
        ExtractedField(document_id=document.id, field_name="item.0", value='{"description":"Carreau","quantity":"8","unit":"carton","unit_price":"13125","discount":null,"line_total":"105000","confidence":1.0}', confidence=0.85, status="RELIABLE"),
        ExtractedField(document_id=document.id, field_name="item.1", value='{"description":"Ciment","quantity":"5","unit":"sac","unit_price":"5040","discount":null,"line_total":"25200","confidence":1.0}', confidence=0.85, status="RELIABLE"),
        ExtractedField(document_id=document.id, field_name="item.2", value='{"description":"Peinture","quantity":"8","unit":"pot","unit_price":"31350","discount":null,"line_total":"250800","confidence":1.0}', confidence=0.85, status="RELIABLE"),
    ])
    db.commit()

    payload = InvoiceCreate(document_id=document_id)
    invoice = InvoiceService().create_draft(db, payload)

    assert invoice.client_id is not None
    assert invoice.currency == "XOF"
    assert invoice.subtotal == Decimal("381000.00")
    assert invoice.discount_total == Decimal("38100.00")
    assert invoice.tax_total == Decimal("61722.00")
    assert invoice.grand_total == Decimal("404622.00")
