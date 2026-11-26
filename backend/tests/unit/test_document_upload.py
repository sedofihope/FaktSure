import asyncio
from io import BytesIO

import pymupdf
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import UploadFile

from app.api.v1.endpoints.batches import upload_documents
from app.db.base import Base
from app.models import Document, DocumentBatch, User


def test_upload_stores_native_pdf_without_starting_extraction(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "A native PDF purchase order")
    content = pdf.tobytes()
    pdf.close()
    saved = {}

    class FakeStorage:
        def save(self, key, payload):
            saved[key] = payload
            return "local", f"/tmp/{key}"

    monkeypatch.setattr("app.storage.manager.StorageManager", FakeStorage)
    try:
        with sessions() as db:
            user = User(
                full_name="Accountant",
                email="upload@example.com",
                password_hash="unused",
                role="ACCOUNTANT",
            )
            db.add(user)
            db.flush()
            batch = DocumentBatch(name="Upload test", created_by=user.id)
            db.add(batch)
            db.commit()

            upload = UploadFile(
                filename="order.pdf",
                file=BytesIO(content),
                headers={"content-type": "application/pdf"},
            )
            response = asyncio.run(upload_documents(batch.public_id, [upload], db, user))

            document = db.query(Document).one()
            assert response["results"][0]["status"] == "uploaded"
            assert document.document_type == "NATIVE_PDF"
            assert document.status == "UPLOADED"
            assert document.storage_backend == "local"
            assert saved[document.storage_key] == content

            duplicate_upload = UploadFile(
                filename="copy.pdf",
                file=BytesIO(content),
                headers={"content-type": "application/pdf"},
            )
            duplicate = asyncio.run(upload_documents(batch.public_id, [duplicate_upload], db, user))
            assert duplicate["results"][0]["status"] == "duplicate"
            assert db.query(Document).count() == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
