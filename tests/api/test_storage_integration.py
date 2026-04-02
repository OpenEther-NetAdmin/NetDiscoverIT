"""
Integration tests for StorageService.

Requires a running MinIO instance. These tests are AUTOMATICALLY SKIPPED if
MINIO_ENDPOINT is not set in the environment, so CI without MinIO is unaffected.

To run manually from the host machine:
    MINIO_ENDPOINT=http://localhost:9000 \
    MINIO_ACCESS_KEY=minioadmin \
    MINIO_SECRET_KEY=minioadmin \
    pytest services/api/tests/api/test_storage_integration.py -v

Or from inside the api container (MinIO is reachable as http://minio:9000):
    docker exec netdiscoverit-api \
        pytest services/api/tests/api/test_storage_integration.py -v
    (MINIO_ENDPOINT is already set in the container via docker-compose)
"""
import os
import pytest
import requests

from app.services.storage import StorageService, StorageError


pytestmark = pytest.mark.skipif(
    not os.getenv("MINIO_ENDPOINT"),
    reason="MINIO_ENDPOINT not set — skipping MinIO integration tests",
)

TEST_BUCKET = "netdiscoverit-test"
TEST_ORG_ID = "00000000-0000-0000-0000-000000000099"


@pytest.fixture(scope="module")
def storage() -> StorageService:
    """
    StorageService pointed at the test MinIO instance with an isolated bucket.
    Creates the test bucket if it doesn't exist (idempotent).
    """
    svc = StorageService()
    svc._bucket = TEST_BUCKET
    try:
        svc.client.create_bucket(Bucket=TEST_BUCKET)
    except Exception:
        pass
    return svc


class TestStorageIntegration:
    def test_upload_and_retrieve(self, storage: StorageService):
        """
        Full round-trip: upload bytes → generate presigned URL → HTTP GET
        the URL → verify the response body matches the original bytes.
        """
        payload = b"integration test payload -- round trip check"
        path = storage.upload_file(TEST_ORG_ID, "integration.txt", payload, "text/plain")

        assert path.startswith(f"exports/{TEST_ORG_ID}/")
        assert path.endswith("integration.txt")

        url = storage.generate_presigned_url(path, expires_seconds=300)
        assert url.startswith("http")

        response = requests.get(url, timeout=10)
        assert response.status_code == 200
        assert response.content == payload

    def test_delete_removes_object(self, storage: StorageService):
        """
        Upload an object, delete it, then verify that generate_presigned_url
        raises StorageError (head_object fails because the object is gone).
        """
        path = storage.upload_file(
            TEST_ORG_ID, "delete-me.txt", b"to be deleted", "text/plain"
        )
        storage.delete_file(path)

        with pytest.raises(StorageError):
            storage.generate_presigned_url(path)
