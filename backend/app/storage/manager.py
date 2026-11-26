import logging
import hashlib
from dataclasses import replace

from app.core.runtime_settings import get_runtime_settings
from app.storage.local import LocalStorage
from app.storage.r2 import R2Storage

logger = logging.getLogger(__name__)


class R2StorageUnavailable(RuntimeError):
    """Raised when an artifact required in R2 cannot be persisted there."""


class StorageManager:
    """Select local storage or an explicitly configured R2-compatible backend."""

    def __init__(self) -> None:
        settings = get_runtime_settings()
        self.local = LocalStorage(settings.storage_root)
        self.remote: R2Storage | None = None
        if settings.r2_enabled:
            try:
                self.remote = R2Storage(
                    account_id=settings.r2_account_id,
                    bucket=settings.r2_bucket,
                    access_key_id=settings.r2_access_key_id,
                    secret_access_key=settings.r2_secret_access_key,
                )
            except ValueError:
                logger.warning(
                    "R2 is enabled but credentials are incomplete; using local storage"
                )

    def save(self, key: str, content: bytes) -> tuple[str, str]:
        local_path = self.local.save(key, content)
        if self.remote is not None:
            try:
                self.remote.save(key, content)
                return "r2", local_path
            except Exception:
                logger.warning("R2 upload failed; retaining document in local fallback storage", exc_info=True)
        return "local", local_path

    def save_essential(self, key: str, content: bytes) -> tuple[str, str]:
        """Persist a required artifact in R2 before attempting a local mirror."""

        if self.remote is None:
            raise R2StorageUnavailable(
                "R2 must be configured to persist essential business files"
            )
        try:
            self.remote.save(key, content)
        except Exception as exc:
            logger.error("Required R2 upload failed", exc_info=True)
            raise R2StorageUnavailable(
                "R2 is unavailable; the essential file was not persisted"
            ) from exc
        try:
            local_path = self.local.save(key, content)
        except OSError:
            logger.warning("R2 copy exists but its local mirror could not be written", exc_info=True)
            local_path = ""
        return "r2", local_path

    def read(self, backend: str, key: str, expected_sha256: str | None = None) -> bytes:
        if backend == "r2":
            if self.remote is not None:
                try:
                    content = self.remote.read(key)
                    self._verify(content, expected_sha256)
                    return content
                except Exception:
                    logger.warning("R2 read failed; using local fallback copy", exc_info=True)
            content = self.local.read(key)
            self._verify(content, expected_sha256)
            return content
        if backend == "local":
            content = self.local.read(key)
            self._verify(content, expected_sha256)
            return content
        raise ValueError(f"Unknown storage backend: {backend}")

    @staticmethod
    def _verify(content: bytes, expected_sha256: str | None) -> None:
        if expected_sha256 is not None:
            actual_sha256 = hashlib.sha256(content).hexdigest()
            if actual_sha256 != expected_sha256:
                raise ValueError("Stored document failed SHA-256 integrity verification")

    def exists(self, backend: str, key: str) -> bool:
        """Check storage, falling back to the local mirror if R2 is unavailable."""

        if backend == "r2":
            if self.remote is not None:
                try:
                    if self.remote.exists(key):
                        return True
                except Exception:
                    logger.warning("R2 existence check failed; checking local fallback", exc_info=True)
            return self.local.exists(key)
        if backend == "local":
            return self.local.exists(key)
        raise ValueError(f"Unknown storage backend: {backend}")

    def delete(self, backend: str, key: str) -> None:
        if backend == "r2":
            if self.remote is not None:
                self.remote.delete(key)
            self.local.delete(key)
            return
        if backend == "local":
            self.local.delete(key)
            return
        raise ValueError(f"Unknown storage backend: {backend}")

    def get_metadata(self, backend: str, key: str):
        if backend == "r2":
            if self.remote is not None:
                try:
                    metadata = self.remote.get_metadata(key)
                    if self.local.exists(key):
                        local_metadata = self.local.get_metadata(key)
                        return replace(metadata, local_path=local_metadata.local_path)
                    return metadata
                except Exception:
                    logger.warning("R2 metadata lookup failed; checking local fallback", exc_info=True)
            metadata = self.local.get_metadata(key)
            return replace(
                metadata,
                storage_backend="r2",
                cloud_sync_status="FAILED",
            )
        if backend == "local":
            return self.local.get_metadata(key)
        raise ValueError(f"Unknown storage backend: {backend}")
