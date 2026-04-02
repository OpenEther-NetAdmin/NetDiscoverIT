"""
Unit tests for StorageService.

All boto3 calls are replaced with MagicMock — no MinIO server is needed.
Tests inject a mock client directly via service._client so the lazy boto3
initialisation never runs.
"""
import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

from app.services.storage import StorageService, StorageError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ORG_ID = "org-abc123"
BUCKET = "test-bucket"


def _make_service() -> tuple[StorageService, MagicMock]:
    """
    Return a StorageService with a mock boto3 client injected.
    Setting service._client bypasses the lazy property so no real boto3
    client is ever created.
    """
    service = StorageService()
    mock_client = MagicMock()
    service._client = mock_client   # inject mock — bypasses lazy init
    service._bucket = BUCKET
    return service, mock_client


def _client_error(code: str) -> ClientError:
    """Build a botocore ClientError with the given error code."""
    return ClientError(
        error_response={"Error": {"Code": code, "Message": code}},
        operation_name="TestOp",
    )


# ---------------------------------------------------------------------------
# upload_file
# ---------------------------------------------------------------------------

class TestUploadFile:
    def test_returns_storage_path_with_correct_format(self):
        """Path must be 'exports/{org_id}/{uuid}-{filename}'."""
        service, _ = _make_service()
        path = service.upload_file(ORG_ID, "report.pdf", b"data", "application/pdf")
        assert path.startswith(f"exports/{ORG_ID}/")
        assert path.endswith("report.pdf")

    def test_storage_path_includes_uuid_prefix(self):
        """Two uploads of the same filename must produce distinct paths."""
        service, _ = _make_service()
        path1 = service.upload_file(ORG_ID, "report.pdf", b"a", "application/pdf")
        path2 = service.upload_file(ORG_ID, "report.pdf", b"b", "application/pdf")
        assert path1 != path2

    def test_calls_put_object_with_correct_args(self):
        """put_object must receive Bucket, Key, Body, and ContentType."""
        service, mock_client = _make_service()
        path = service.upload_file(ORG_ID, "report.pdf", b"hello", "application/pdf")
        mock_client.put_object.assert_called_once_with(
            Bucket=BUCKET,
            Key=path,
            Body=b"hello",
            ContentType="application/pdf",
        )

    def test_raises_storage_error_on_client_error(self):
        """boto3 ClientError must be re-raised as StorageError."""
        service, mock_client = _make_service()
        mock_client.put_object.side_effect = _client_error("NoSuchBucket")
        with pytest.raises(StorageError) as exc_info:
            service.upload_file(ORG_ID, "report.pdf", b"data", "application/pdf")
        assert exc_info.value.original_error is not None


# ---------------------------------------------------------------------------
# generate_presigned_url
# ---------------------------------------------------------------------------

class TestGeneratePresignedUrl:
    def test_calls_head_object_before_signing(self):
        """head_object must be called to verify existence before generating the URL."""
        service, mock_client = _make_service()
        mock_client.generate_presigned_url.return_value = "https://minio/signed"
        path = "exports/org-abc123/uuid-report.pdf"
        service.generate_presigned_url(path)
        mock_client.head_object.assert_called_once_with(Bucket=BUCKET, Key=path)

    def test_calls_generate_presigned_url_with_correct_params(self):
        """generate_presigned_url must pass method='get_object', Bucket, Key, ExpiresIn."""
        service, mock_client = _make_service()
        mock_client.generate_presigned_url.return_value = "https://minio/signed"
        path = "exports/org-abc123/uuid-report.pdf"
        service.generate_presigned_url(path, expires_seconds=1800)
        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": BUCKET, "Key": path},
            ExpiresIn=1800,
        )

    def test_uses_default_expiry_from_settings(self):
        """When expires_seconds is None, settings.MINIO_PRESIGNED_EXPIRY_SECONDS is used."""
        service, mock_client = _make_service()
        mock_client.generate_presigned_url.return_value = "https://minio/signed"
        path = "exports/org-abc123/uuid-report.pdf"
        with patch("app.services.storage.settings") as mock_settings:
            mock_settings.MINIO_PRESIGNED_EXPIRY_SECONDS = 7200
            service.generate_presigned_url(path)
        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": BUCKET, "Key": path},
            ExpiresIn=7200,
        )

    def test_raises_storage_error_when_object_missing(self):
        """head_object failure (object not found) must raise StorageError immediately."""
        service, mock_client = _make_service()
        mock_client.head_object.side_effect = _client_error("404")
        with pytest.raises(StorageError) as exc_info:
            service.generate_presigned_url("exports/org-abc123/missing.pdf")
        assert exc_info.value.original_error is not None

    def test_returns_url_string(self):
        """The return value must be the signed URL string from boto3."""
        service, mock_client = _make_service()
        mock_client.generate_presigned_url.return_value = "https://minio:9000/signed?token=abc"
        url = service.generate_presigned_url("exports/org-abc123/uuid-report.pdf")
        assert url == "https://minio:9000/signed?token=abc"


# ---------------------------------------------------------------------------
# delete_file
# ---------------------------------------------------------------------------

class TestDeleteFile:
    def test_calls_delete_object_with_correct_args(self):
        """delete_object must receive the correct Bucket and Key."""
        service, mock_client = _make_service()
        path = "exports/org-abc123/uuid-report.pdf"
        service.delete_file(path)
        mock_client.delete_object.assert_called_once_with(Bucket=BUCKET, Key=path)

    def test_is_noop_for_missing_object(self):
        """NoSuchKey ClientError must be silently swallowed (idempotent delete)."""
        service, mock_client = _make_service()
        mock_client.delete_object.side_effect = _client_error("NoSuchKey")
        service.delete_file("exports/org-abc123/missing.pdf")   # must not raise

    def test_raises_storage_error_on_unexpected_error(self):
        """Any error other than NoSuchKey must be re-raised as StorageError."""
        service, mock_client = _make_service()
        mock_client.delete_object.side_effect = _client_error("AccessDenied")
        with pytest.raises(StorageError) as exc_info:
            service.delete_file("exports/org-abc123/uuid-report.pdf")
        assert exc_info.value.original_error is not None
