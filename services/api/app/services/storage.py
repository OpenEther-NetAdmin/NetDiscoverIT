"""
Object storage service — S3-compatible wrapper using boto3.

Provides upload, presigned URL generation, and delete operations against MinIO
(or any S3-compatible store). Swap the endpoint by changing MINIO_ENDPOINT in
your environment — no code changes required for AWS S3, Cloudflare R2, etc.

Usage (from Celery workers or API routes):
    from app.services.storage import storage_service, StorageError

    path = storage_service.upload_file(org_id, "report.pdf", pdf_bytes, "application/pdf")
    url  = storage_service.generate_presigned_url(path)
    storage_service.delete_file(path)
"""
from __future__ import annotations

import logging
import uuid

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Raised for any object storage operation failure.

    Attributes:
        original_error: The underlying botocore ClientError, if any.
                        Callers (e.g. Celery tasks) can log this for full detail.
    """

    def __init__(self, message: str, original_error: Exception | None = None) -> None:
        super().__init__(message)
        self.original_error = original_error


class StorageService:
    """S3-compatible object storage wrapper.

    Thread-safe. Safe to use from Celery workers.
    The boto3 client is created lazily on first use — the API starts cleanly
    even if MinIO is temporarily unavailable at startup.
    """

    def __init__(self) -> None:
        # Client created lazily via the `client` property on first use.
        self._client = None
        self._bucket = settings.MINIO_BUCKET

    @property
    def client(self):
        """Return (or create) the boto3 S3 client."""
        if self._client is None:
            if not settings.MINIO_ACCESS_KEY or not settings.MINIO_SECRET_KEY:
                raise StorageError(
                    "MINIO_ACCESS_KEY and MINIO_SECRET_KEY must be set before "
                    "using StorageService. Add them to your .env file."
                )
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.MINIO_ENDPOINT,
                aws_access_key_id=settings.MINIO_ACCESS_KEY,
                aws_secret_access_key=settings.MINIO_SECRET_KEY,
            )
        return self._client

    def upload_file(
        self,
        org_id: str,
        filename: str,
        data: bytes,
        content_type: str,
    ) -> str:
        """Upload *data* to object storage.

        Args:
            org_id:       Organisation UUID string — used to namespace the path.
            filename:     Human-readable filename suffix (e.g. ``"report.pdf"``).
            data:         Raw file bytes.
            content_type: MIME type (e.g. ``"application/pdf"``).

        Returns:
            storage_path: ``"exports/{org_id}/{uuid4}-{filename}"`` — persist this
            on ``ExportDocument.storage_path``.

        Raises:
            StorageError: If the upload fails for any reason.
        """
        storage_path = f"exports/{org_id}/{uuid.uuid4()}-{filename}"
        try:
            self.client.put_object(
                Bucket=self._bucket,
                Key=storage_path,
                Body=data,
                ContentType=content_type,
            )
        except ClientError as exc:
            logger.error("MinIO upload failed for %s: %s", storage_path, exc, exc_info=True)
            raise StorageError(f"Upload failed: {exc}", original_error=exc) from exc
        logger.info("Uploaded %d bytes → %s", len(data), storage_path)
        return storage_path

    def generate_presigned_url(
        self,
        storage_path: str,
        expires_seconds: int | None = None,
    ) -> str:
        """Return a time-limited presigned GET URL for *storage_path*.

        Calls ``head_object`` first so callers get a ``StorageError`` immediately
        if the object is missing, rather than a 403/404 when the user tries to
        download.

        Args:
            storage_path:    Value previously returned by ``upload_file``.
            expires_seconds: URL lifetime. Defaults to
                             ``settings.MINIO_PRESIGNED_EXPIRY_SECONDS`` (3600).

        Returns:
            Presigned URL string valid for *expires_seconds* seconds.

        Raises:
            StorageError: If the object is missing or the URL cannot be generated.
        """
        if expires_seconds is None:
            expires_seconds = settings.MINIO_PRESIGNED_EXPIRY_SECONDS
        try:
            self.client.head_object(Bucket=self._bucket, Key=storage_path)
        except ClientError as exc:
            logger.error(
                "head_object failed for %s: %s", storage_path, exc, exc_info=True
            )
            raise StorageError(
                f"Object not found or inaccessible: {storage_path}",
                original_error=exc,
            ) from exc
        url: str = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": storage_path},
            ExpiresIn=expires_seconds,
        )
        return url

    def delete_file(self, storage_path: str) -> None:
        """Delete the object at *storage_path*.

        Idempotent — no-op if the object does not exist, so retry scenarios
        and double-deletes are safe.

        Raises:
            StorageError: On any failure other than the object not existing.
        """
        try:
            self.client.delete_object(Bucket=self._bucket, Key=storage_path)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code == "NoSuchKey":
                return  # already gone — that's fine
            logger.error(
                "MinIO delete failed for %s: %s", storage_path, exc, exc_info=True
            )
            raise StorageError(f"Delete failed: {exc}", original_error=exc) from exc
        logger.info("Deleted %s", storage_path)


# Module-level singleton — safe to import at startup because the boto3 client
# is created lazily (only when the first storage method is called).
storage_service = StorageService()
