import hashlib
from types import SimpleNamespace

import pytest

from app.storage.local import LocalStorage
from app.storage.manager import R2StorageUnavailable, StorageManager
from app.storage.r2 import R2Storage


def test_local_storage_rejects_path_traversal(tmp_path):
    storage = LocalStorage(tmp_path / "objects")

    with pytest.raises(ValueError, match="within the storage root"):
        storage.save("../outside.txt", b"private")


def test_storage_manager_uses_local_if_r2_is_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.storage.manager.get_runtime_settings",
        lambda: SimpleNamespace(storage_root=tmp_path, r2_enabled=False),
    )
    manager = StorageManager()

    backend, local_path = manager.save("batch/digest", b"document")

    assert backend == "local"
    assert manager.read(backend, "batch/digest", hashlib.sha256(b"document").hexdigest()) == b"document"
    assert local_path.endswith("batch/digest")


def test_r2_upload_and_read_use_s3_compatible_calls(monkeypatch):
    calls = {}

    class Body:
        def read(self):
            return b"pdf"

        def close(self):
            pass

    class FakeClient:
        def put_object(self, **kwargs):
            calls["put"] = kwargs

        def get_object(self, **kwargs):
            calls["get"] = kwargs
            return {"Body": Body()}

    monkeypatch.setattr("app.storage.r2.boto3.client", lambda *args, **kwargs: FakeClient())
    storage = R2Storage("account", "bucket", "access", "secret")
    storage.save("1/hash", b"pdf")

    assert calls["put"]["Bucket"] == "bucket"
    assert calls["put"]["Metadata"]["sha256"] == hashlib.sha256(b"pdf").hexdigest()
    assert storage.read("1/hash") == b"pdf"


def test_storage_manager_falls_back_to_local_on_r2_failure(tmp_path, monkeypatch, caplog):
    class UnavailableR2:
        def __init__(self, **_kwargs):
            pass

        def save(self, _key, _content):
            raise ConnectionError("R2 unavailable")

        def read(self, _key):
            raise ConnectionError("R2 unavailable")

    monkeypatch.setattr(
        "app.storage.manager.get_runtime_settings",
        lambda: SimpleNamespace(
            storage_root=tmp_path,
            r2_enabled=True,
            r2_account_id="account",
            r2_bucket="bucket",
            r2_access_key_id="access",
            r2_secret_access_key="secret",
        ),
    )
    monkeypatch.setattr("app.storage.manager.R2Storage", UnavailableR2)
    manager = StorageManager()

    backend, _local_path = manager.save("1/hash", b"pdf")

    assert backend == "local"
    assert manager.read("local", "1/hash", hashlib.sha256(b"pdf").hexdigest()) == b"pdf"
    assert "R2 upload failed" in caplog.text


def test_essential_artifact_requires_successful_r2_write(tmp_path, monkeypatch):
    class UnavailableR2:
        def __init__(self, **_kwargs):
            pass

        def save(self, _key, _content):
            raise ConnectionError("R2 unavailable")

    monkeypatch.setattr(
        "app.storage.manager.get_runtime_settings",
        lambda: SimpleNamespace(
            storage_root=tmp_path,
            r2_enabled=True,
            r2_account_id="account",
            r2_bucket="bucket",
            r2_access_key_id="access",
            r2_secret_access_key="secret",
        ),
    )
    monkeypatch.setattr("app.storage.manager.R2Storage", UnavailableR2)
    manager = StorageManager()

    with pytest.raises(R2StorageUnavailable, match="not persisted"):
        manager.save_essential("invoices/invoice.pdf", b"pdf")


def test_essential_artifact_is_written_to_r2_before_local_mirror(tmp_path, monkeypatch):
    calls = []

    class FakeR2:
        def __init__(self, **_kwargs):
            pass

        def save(self, key, content):
            calls.append(("r2", key, content))

    monkeypatch.setattr(
        "app.storage.manager.get_runtime_settings",
        lambda: SimpleNamespace(
            storage_root=tmp_path,
            r2_enabled=True,
            r2_account_id="account",
            r2_bucket="bucket",
            r2_access_key_id="access",
            r2_secret_access_key="secret",
        ),
    )
    monkeypatch.setattr("app.storage.manager.R2Storage", FakeR2)
    manager = StorageManager()
    original_local_save = manager.local.save

    def track_local_save(key, content):
        calls.append(("local", key, content))
        return original_local_save(key, content)

    monkeypatch.setattr(manager.local, "save", track_local_save)
    backend, local_path = manager.save_essential("invoices/invoice.pdf", b"pdf")

    assert backend == "r2"
    assert local_path.endswith("invoices/invoice.pdf")
    assert [call[0] for call in calls] == ["r2", "local"]


def test_r2_metadata_reads_and_exists_fall_back_to_local_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.storage.manager.get_runtime_settings",
        lambda: SimpleNamespace(storage_root=tmp_path, r2_enabled=False),
    )
    manager = StorageManager()
    manager.local.save("documents/test.pdf", b"pdf")

    assert manager.read("r2", "documents/test.pdf") == b"pdf"
    assert manager.exists("r2", "documents/test.pdf")
    metadata = manager.get_metadata("r2", "documents/test.pdf")
    assert metadata.storage_backend == "r2"
    assert metadata.cloud_sync_status == "FAILED"
    assert metadata.sha256 == hashlib.sha256(b"pdf").hexdigest()


def test_local_storage_metadata_and_delete(tmp_path):
    storage = LocalStorage(tmp_path / "objects")
    storage.save("documents/test.pdf", b"pdf")

    metadata = storage.get_metadata("documents/test.pdf")
    assert metadata.size_bytes == 3
    assert metadata.cloud_sync_status == "LOCAL_ONLY"
    storage.delete("documents/test.pdf")
    assert not storage.exists("documents/test.pdf")
