from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.document import Document
from app.models.document_batch import DocumentBatch
from app.models.user import User
from app.services import batch_service


def build_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def seed_batch(session_factory, document_count=1):
    with session_factory() as db:
        user = User(
            full_name="Test User",
            email="test@example.com",
            password_hash="not-used",
            role="ACCOUNTANT",
        )
        db.add(user)
        db.flush()
        batch = DocumentBatch(name="Test batch", created_by=user.id, status="PROCESSING")
        db.add(batch)
        db.flush()
        documents = []
        for index in range(document_count):
            document = Document(
                batch_id=batch.id,
                original_filename=f"doc-{index}.pdf",
                mime_type="application/pdf",
                file_size=4,
                document_type="NATIVE_PDF",
                storage_backend="local",
                storage_key=f"batch/{index}",
                sha256=str(index),
                status="QUEUED",
            )
            db.add(document)
            documents.append(document)
        db.commit()
        return batch.id, [doc.id for doc in documents]


def test_batch_worker_processes_queued_documents_sequentially(monkeypatch):
    session_factory = build_session_factory()
    batch_id, document_ids = seed_batch(session_factory, document_count=2)
    call_order = []

    class FakeStorage:
        def read(self, backend, key, digest):
            return key.encode()

    class FakeExtraction:
        def extract(self, db, document, content, actor_id=None):
            call_order.append(document.id)
            document.status = "REVIEW_REQUIRED"
            db.commit()

    monkeypatch.setattr(batch_service, "SessionLocal", session_factory)
    monkeypatch.setattr(
        batch_service,
        "get_runtime_settings",
        lambda: SimpleNamespace(document_batch_size=3, max_document_concurrency=1),
    )
    monkeypatch.setattr(batch_service, "StorageManager", FakeStorage)
    monkeypatch.setattr(batch_service, "ExtractionService", FakeExtraction)

    batch_service.process_batch_in_background(batch_id)

    assert call_order == document_ids
    with session_factory() as db:
        batch = db.get(DocumentBatch, batch_id)
        assert batch.status == "COMPLETED"
        assert batch.processed_documents == 2
        assert batch.failed_documents == 0


def test_batch_worker_marks_failed_documents_and_completes_partially(monkeypatch):
    session_factory = build_session_factory()
    batch_id, document_ids = seed_batch(session_factory)

    class FakeStorage:
        def read(self, backend, key, digest):
            raise OSError("private infrastructure detail")

    monkeypatch.setattr(batch_service, "SessionLocal", session_factory)
    monkeypatch.setattr(
        batch_service,
        "get_runtime_settings",
        lambda: SimpleNamespace(document_batch_size=3, max_document_concurrency=1),
    )
    monkeypatch.setattr(batch_service, "StorageManager", FakeStorage)

    batch_service.process_batch_in_background(batch_id)

    with session_factory() as db:
        batch = db.get(DocumentBatch, batch_id)
        document = db.get(Document, document_ids[0])
        assert batch.status == "PARTIALLY_COMPLETED"
        assert batch.failed_documents == 1
        assert document.status == "FAILED"
        assert document.error_message == "Processing failed: OSError"


def test_recovery_requeues_interrupted_extraction(monkeypatch):
    session_factory = build_session_factory()
    batch_id, document_ids = seed_batch(session_factory)
    with session_factory() as db:
        document = db.get(Document, document_ids[0])
        document.status = "EXTRACTING"
        db.commit()
    monkeypatch.setattr(batch_service, "SessionLocal", session_factory)

    recovered = batch_service.recover_interrupted_batches()

    assert recovered == [batch_id]
    with session_factory() as db:
        document = db.get(Document, document_ids[0])
        assert document.status == "QUEUED"
