from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Dict, Iterable, Optional

from .config import Settings


class StorageError(RuntimeError):
    pass


class StorageDisabled(StorageError):
    pass


@dataclass(frozen=True)
class StoredObject:
    key: str
    etag: Optional[str]


class DisabledStorage:
    def ensure_ready(self) -> None:
        return None

    def healthcheck(self) -> str:
        return "disabled"

    def put(self, relative_key: str, body: bytes, content_type: str) -> StoredObject:
        raise StorageDisabled("S3 storage is disabled")

    def presigned_get(self, relative_key: str) -> str:
        raise StorageDisabled("S3 storage is disabled")

    def get(self, relative_key: str) -> bytes:
        raise StorageDisabled("S3 storage is disabled")

    def delete(self, relative_key: str) -> None:
        raise StorageDisabled("S3 storage is disabled")


class S3Storage:
    def __init__(self, settings: Settings, client: Any = None) -> None:
        settings.validate_s3_credentials()
        self.bucket = settings.s3_bucket
        self.prefix = settings.s3_prefix
        self.presigned_ttl = settings.s3_presigned_ttl_seconds
        self.presign_client = client
        if client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError as exc:
                raise StorageError("boto3 is required for S3 storage") from exc
            # Контрольные суммы только по требованию: S3-совместимые хранилища (Beget и др.)
            # отклоняют CRC32-заголовки, которые boto3 >= 1.36 добавляет по умолчанию.
            config = Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            )
            client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint,
                region_name=settings.s3_region,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                config=config,
            )
            presign_endpoint = settings.s3_presign_endpoint or settings.s3_endpoint
            self.presign_client = (
                client
                if presign_endpoint == settings.s3_endpoint
                else boto3.client(
                    "s3",
                    endpoint_url=presign_endpoint,
                    region_name=settings.s3_region,
                    aws_access_key_id=settings.s3_access_key,
                    aws_secret_access_key=settings.s3_secret_key,
                    config=config,
                )
            )
        self.client = client

    def _key(self, relative_or_stored_key: str) -> str:
        candidate = relative_or_stored_key.strip().lstrip("/")
        path = PurePosixPath(candidate)
        if not candidate or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise StorageError("Unsafe storage key")
        if candidate.startswith(f"{self.prefix}/"):
            return path.as_posix()
        return f"{self.prefix}/{path.as_posix()}"

    def ensure_ready(self) -> None:
        self.client.list_objects_v2(Bucket=self.bucket, Prefix=f"{self.prefix}/", MaxKeys=1)

    def healthcheck(self) -> str:
        try:
            self.ensure_ready()
            return "ok"
        except Exception as exc:  # provider-specific boto exception hierarchy
            return f"error:{type(exc).__name__}"

    def put(self, relative_key: str, body: bytes, content_type: str) -> StoredObject:
        key = self._key(relative_key)
        response = self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
        return StoredObject(key=key, etag=response.get("ETag"))

    def presigned_get(self, relative_key: str) -> str:
        key = self._key(relative_key)
        return self.presign_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=self.presigned_ttl,
        )

    def get(self, relative_key: str) -> bytes:
        key = self._key(relative_key)
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def delete(self, relative_key: str) -> None:
        key = self._key(relative_key)
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def delete_project_objects(self) -> int:
        """Delete only objects below the configured project prefix."""
        prefix = f"{self.prefix}/"
        deleted = 0
        continuation: Optional[str] = None
        while True:
            request: Dict[str, Any] = {"Bucket": self.bucket, "Prefix": prefix}
            if continuation:
                request["ContinuationToken"] = continuation
            page = self.client.list_objects_v2(**request)
            objects = [
                {"Key": item["Key"]}
                for item in page.get("Contents", [])
                if item.get("Key", "").startswith(prefix)
            ]
            if objects:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objects, "Quiet": True})
                deleted += len(objects)
            if not page.get("IsTruncated"):
                return deleted
            continuation = page.get("NextContinuationToken")
            if not continuation:
                raise StorageError("S3 pagination was truncated without a continuation token")
