import hashlib


def sha256_bytes(content: bytes) -> str:
    """Return the lowercase SHA-256 digest of bytes."""

    return hashlib.sha256(content).hexdigest()
