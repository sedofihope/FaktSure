from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1.endpoints.clients import update_client
from app.api.v1.endpoints.documents import correct_fields
from app.api.v1.endpoints.products import update_product
from app.core.exceptions import ConflictError
from app.db.base import Base
from app.models import AuditLog, Client, Document, DocumentBatch, ExtractedField, Invoice, Product, User
from app.schemas.anomaly import CorrectFieldsRequest, FieldCorrection
from app.schemas.client import ClientUpdate
from app.schemas.product import ProductUpdate


def test_partial_client_and_product_updates_preserve_omitted_values():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        user = User(
            full_name="Editor",
            email="editor@example.com",
            password_hash="unused",
            role="ADMIN",
        )
        client = Client(name="Client", email="client@example.com", address="Old")
        product = Product(sku="SKU-1", name="Product", description="Old")
        db.add_all([user, client, product])
        db.commit()

        updated_client = update_client(
            client.public_id,
            ClientUpdate(address="New"),
            db,
            user,
        )
        updated_product = update_product(
            product.public_id,
            ProductUpdate(description="New"),
            db,
            user,
        )

        assert updated_client.name == "Client"
        assert updated_client.email == "client@example.com"
        assert updated_client.address == "New"
        assert updated_product.sku == "SKU-1"
        assert updated_product.name == "Product"
        assert updated_product.description == "New"
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_correction_after_review_invalidates_approval_and_is_audited():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        user = User(
            full_name="Reviewer",
            email="reviewer@example.com",
            password_hash="unused",
            role="ACCOUNTANT",
        )
        db.add(user)
        db.flush()
        batch = DocumentBatch(name="Reviewed", created_by=user.id)
        db.add(batch)
        db.flush()
        document = Document(
            batch_id=batch.id,
            original_filename="reviewed.pdf",
            mime_type="application/pdf",
            file_size=3,
            document_type="NATIVE_PDF",
            storage_key="reviewed.pdf",
            sha256="digest",
            status="READY",
        )
        db.add(document)
        db.flush()
        db.add(ExtractedField(
            document_id=document.id,
            field_name="document_number",
            value="OLD-1",
            confidence=0.9,
            status="RELIABLE",
        ))
        db.commit()

        correct_fields(
            document.public_id,
            CorrectFieldsRequest(corrections=[
                FieldCorrection(field_name="document_number", corrected_value="NEW-1"),
            ]),
            db,
            user,
        )

        assert document.status == "REVIEW_REQUIRED"
        assert db.query(AuditLog).filter_by(
            action="DOCUMENT_REVIEW_INVALIDATED"
        ).count() == 1

        invoice = Invoice(
            document_id=document.id,
            invoice_number="DRAFT-1",
            issue_date=date(2026, 11, 25),
            currency="XOF",
            status="DRAFT",
        )
        db.add(invoice)
        db.commit()
        document.status = "READY"
        db.commit()

        try:
            correct_fields(
                document.public_id,
                CorrectFieldsRequest(corrections=[
                    FieldCorrection(field_name="document_number", corrected_value="NEW-2"),
                ]),
                db,
                user,
            )
        except ConflictError:
            pass
        else:
            raise AssertionError("Correction must be blocked after invoice draft creation")
    Base.metadata.drop_all(engine)
    engine.dispose()
from datetime import date
