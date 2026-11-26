import json
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    Anomaly,
    Client,
    Document,
    DocumentBatch,
    ExtractedField,
    Product,
    ProductPrice,
    User,
)
from app.schemas.anomaly import ResolveAnomalyRequest
from app.validators.anomaly_detector import AnomalyDetector


def test_detector_reports_reference_price_quantity_and_totals():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with sessions() as db:
            user = User(
                full_name="Tester",
                email="tester@example.com",
                password_hash="unused",
                role="ACCOUNTANT",
            )
            db.add(user)
            db.flush()
            client = Client(name="Demo Client")
            product = Product(sku="SKU-1", name="Widget")
            db.add_all([client, product])
            db.flush()
            db.add(ProductPrice(
                product_id=product.id,
                unit_price=100,
                currency="XOF",
                valid_from=date(2026, 1, 1),
            ))
            batch = DocumentBatch(name="Batch", created_by=user.id)
            db.add(batch)
            db.flush()
            document = Document(
                batch_id=batch.id,
                original_filename="order.pdf",
                mime_type="application/pdf",
                file_size=20,
                document_type="NATIVE_PDF",
                storage_key="batch/hash",
                sha256="hash",
                status="REVIEW_REQUIRED",
            )
            db.add(document)
            db.flush()
            values = {
                "client_name": "Demo Client",
                "document_date": "2026-10-10",
                "document_number": "PO-123",
                "currency": "XOF",
                "subtotal": "100",
                "tax_total": "0",
                "grand_total": "100",
                "item.0": json.dumps({
                    "description": "Widget",
                    "sku": "SKU-1",
                    "quantity": "1001",
                    "unit_price": "120",
                    "discount": "0",
                    "line_total": "120",
                }),
            }
            for name, value in values.items():
                db.add(ExtractedField(
                    document_id=document.id,
                    field_name=name,
                    value=value,
                    confidence=0.9,
                    status="RELIABLE",
                ))
            db.commit()

            anomalies = AnomalyDetector().detect(db, document)

            types = {anomaly.anomaly_type for anomaly in anomalies}
            assert "PRICE_MISMATCH" in types
            assert "QUANTITY_UNUSUAL" in types
            assert "TOTAL_MISMATCH" in types
            assert "CONTRADICTORY_FIELD" in types
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_detector_matches_client_by_rccm_when_name_differs():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with sessions() as db:
            user = User(
                full_name="Tester",
                email="rccm@example.com",
                password_hash="unused",
                role="ACCOUNTANT",
            )
            client = Client(name="Registered Client", rccm="SN-DKR-2026-B-00001")
            db.add_all([user, client])
            db.flush()
            batch = DocumentBatch(name="Batch", created_by=user.id)
            db.add(batch)
            db.flush()
            document = Document(
                batch_id=batch.id,
                original_filename="order.pdf",
                mime_type="application/pdf",
                file_size=20,
                document_type="NATIVE_PDF",
                storage_key="batch/rccm",
                sha256="rccm-test",
                status="REVIEW_REQUIRED",
            )
            db.add(document)
            db.flush()
            for name, value in {
                "client_name": "Name on document differs",
                "client_rccm": "sn-dkr-2026-b-00001",
            }.items():
                db.add(ExtractedField(
                    document_id=document.id,
                    field_name=name,
                    value=value,
                    confidence=0.9,
                    status="RELIABLE",
                ))
            db.commit()

            anomalies = AnomalyDetector().detect(db, document)

            assert "CLIENT_UNKNOWN" not in {anomaly.anomaly_type for anomaly in anomalies}
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_discounted_taxable_base_total_can_resolve_blocker():
    from app.api.v1.endpoints.documents import resolve_blocker

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with sessions() as db:
            user = User(
                full_name="Tester",
                email="discount-total@example.com",
                password_hash="unused",
                role="ACCOUNTANT",
            )
            db.add(user)
            db.flush()
            db.add(Client(name="Demo Client"))
            batch = DocumentBatch(name="Discount test", created_by=user.id)
            db.add(batch)
            db.flush()
            document = Document(
                batch_id=batch.id,
                original_filename="discounted-order.pdf",
                mime_type="application/pdf",
                file_size=20,
                document_type="NATIVE_PDF",
                storage_key="batch/discount",
                sha256="discount-total-test",
                status="REVIEW_REQUIRED",
            )
            db.add(document)
            db.flush()
            values = {
                "client_name": "Demo Client",
                "document_date": "2026-11-25",
                "document_number": "PO-DISCOUNT-1",
                "currency": "XOF",
                "subtotal": "381000",
                "discount_total": "38100",
                "tax_total": "61722",
                "grand_total": "404622",
                "item.0": json.dumps({
                    "description": "Service",
                    "quantity": 8,
                    "unit_price": 13125,
                    "discount": 0,
                    "line_total": 105000,
                }),
                "item.1": json.dumps({
                    "description": "Goods",
                    "quantity": 5,
                    "unit_price": 5040,
                    "discount": 0,
                    "line_total": 25200,
                }),
                "item.2": json.dumps({
                    "description": "Equipment",
                    "quantity": 8,
                    "unit_price": 31350,
                    "discount": 0,
                    "line_total": 250800,
                }),
            }
            for name, value in values.items():
                db.add(ExtractedField(
                    document_id=document.id,
                    field_name=name,
                    value=value,
                    confidence=0.9,
                    status="RELIABLE",
                ))
            mismatch = Anomaly(
                document_id=document.id,
                field_name="grand_total",
                anomaly_type="TOTAL_MISMATCH",
                severity="BLOCKER",
                description="Subtotal plus tax does not equal grand total",
                expected_value="442722",
                actual_value="404622",
                status="OPEN",
            )
            db.add(mismatch)
            db.commit()

            assert mismatch.expected_value == "442722"
            assert mismatch.actual_value == "404622"
            mismatch_public_id = mismatch.public_id

            response = resolve_blocker(
                document.public_id,
                mismatch_public_id,
                ResolveAnomalyRequest(
                    field_name="grand_total",
                    corrected_value="404622",
                    resolution_note="Tax is applied after discount.",
                ),
                db,
                user,
            )

            assert response == {
                "status": "resolved",
                "anomaly_id": str(mismatch_public_id),
            }
            assert not db.query(Anomaly).filter(
                Anomaly.document_id == document.id,
                Anomaly.severity == "BLOCKER",
                Anomaly.status == "OPEN",
            ).count()
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()