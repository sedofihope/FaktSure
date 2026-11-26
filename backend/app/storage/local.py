import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StorageMetadata:
    storage_backend: str
    object_key: str
    local_path: str | None
    sha256: str
    size_bytes: int
    cloud_sync_status: str


class LocalStorage:
    """Persist original documents on the local filesystem."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Storage key must remain within the storage root")
        return path

    def save(self, key: str, content: bytes) -> str:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path)

    def read(self, key: str) -> bytes:
        path = self._path_for(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path_for(key).is_file()

    def delete(self, key: str) -> None:
        path = self._path_for(key)
        path.unlink(missing_ok=True)

    def get_metadata(self, key: str) -> StorageMetadata:
        path = self._path_for(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        content = path.read_bytes()
        return StorageMetadata(
            storage_backend="local",
            object_key=key,
            local_path=str(path),
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            cloud_sync_status="LOCAL_ONLY",
        )
