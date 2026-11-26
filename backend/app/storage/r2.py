from __future__ import annotations

import hashlib
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.storage.local import StorageMetadata


class R2Storage:
    """Cloudflare R2 adapter using its S3-compatible API."""

    def __init__(self, account_id: str, bucket: str, access_key_id: str, secret_access_key: str) -> None:
        if not all((account_id, bucket, access_key_id, secret_access_key)):
            raise ValueError("R2 account, bucket, access key, and secret key are required")
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
            config=Config(signature_version="s3v4"),
        )

    def save(self, key: str, content: bytes) -> None:
        """Upload document bytes and their SHA-256 metadata."""

        checksum = hashlib.sha256(content).hexdigest()
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            Metadata={"sha256": checksum},
        )

    def read(self, key: str) -> bytes:
        """Download a document from R2."""

        response: dict[str, Any] = self.client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"]
        try:
            return body.read()
        finally:
            body.close()

    def exists(self, key: str) -> bool:
        """Return whether an object exists in R2."""

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
                return False
            raise
        return True

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def get_metadata(self, key: str) -> StorageMetadata:
        response: dict[str, Any] = self.client.head_object(
            Bucket=self.bucket,
            Key=key,
        )
        return StorageMetadata(
            storage_backend="r2",
            object_key=key,
            local_path=None,
            sha256=response.get("Metadata", {}).get("sha256", ""),
            size_bytes=response["ContentLength"],
            cloud_sync_status="SYNCED",
        )