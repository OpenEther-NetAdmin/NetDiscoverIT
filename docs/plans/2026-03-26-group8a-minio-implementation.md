# Group 8a — MinIO Object Storage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MinIO S3-compatible object storage to the Docker stack and expose a `StorageService` wrapper (`upload_file`, `generate_presigned_url`, `delete_file`) for use by Group 8b compliance report generation.

**Architecture:** MinIO runs as two Docker services (`minio` + one-shot `minio-init` bucket creator). The API accesses it via `boto3` in S3-compatible mode — changing `MINIO_ENDPOINT` to an AWS/Cloudflare endpoint requires zero code changes. `StorageService` is a thin wrapper that keeps boto3 types out of callers; all errors surface as `StorageError`. The boto3 client is created lazily on first use so the API starts cleanly even if MinIO is temporarily unavailable.

**Tech Stack:** `boto3>=1.34.0`, MinIO `RELEASE.2024-01-16T16-07-38Z`, FastAPI (existing), pytest + unittest.mock (existing).

**Design spec:** `docs/plans/2026-03-26-group8a-minio-design.md`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `services/api/requirements.txt` | Add `boto3>=1.34.0` |
| Modify | `services/api/app/core/config.py` | Add 5 `MINIO_*` settings |
| Modify | `.env.example` | Add `MINIO_*` vars with comments |
| Modify | `docker-compose.yml` | Add `minio`, `minio-init` services; `minio_data` volume; MINIO env vars on `api` service |
| Create | `services/api/app/services/storage.py` | `StorageError` exception + `StorageService` class + module-level singleton |
| Create | `services/api/tests/api/test_storage_unit.py` | 11 unit tests — boto3 fully mocked |
| Create | `services/api/tests/api/test_storage_integration.py` | 2 integration tests — real MinIO, auto-skipped if `MINIO_ENDPOINT` unset |

---

## Task 1: Dependencies, Config, and Env Vars

**Files:**
- Modify: `services/api/requirements.txt`
- Modify: `services/api/app/core/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add boto3 to requirements.txt**

Open `services/api/requirements.txt`. Add after the `# NLI / RAG` block at the bottom:

```
# Object Storage (MinIO / S3-compatible)
boto3==1.34.0
```

- [ ] **Step 2: Add MINIO settings to config.py**

Open `services/api/app/core/config.py`. Add after the `# NLI / RAG` block (before `settings = Settings()`):

```python
    # Object Storage (MinIO / S3-compatible)
    # MINIO_ACCESS_KEY and MINIO_SECRET_KEY are Optional so the app starts
    # cleanly without MinIO configured. The first actual storage call raises
    # StorageError if they are unset.
    MINIO_ENDPOINT: str = "http://minio:9000"
    MINIO_ACCESS_KEY: str | None = None
    MINIO_SECRET_KEY: str | None = None
    MINIO_BUCKET: str = "netdiscoverit"
    MINIO_PRESIGNED_EXPIRY_SECONDS: int = 3600  # 1 hour
```

- [ ] **Step 3: Add MINIO vars to .env.example**

Open `.env.example`. Add a new section after the `# CORS` section:

```
# =============================================================================
# OBJECT STORAGE (MinIO — S3-compatible)
# MinIO runs as a Docker service. These are also the MinIO server credentials.
# Default credentials below match the docker-compose minio service.
# For production, replace with strong random values or use AWS S3 vars.
# =============================================================================
MINIO_ENDPOINT=http://minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=netdiscoverit
MINIO_PRESIGNED_EXPIRY_SECONDS=3600
```

- [ ] **Step 4: Run existing test suite — confirm nothing broken**

```bash
cd /home/openether/NetDiscoverIT
docker exec netdiscoverit-api pytest services/api/tests/ -v --tb=short -q 2>&1 | tail -20
```

Expected: all existing tests pass (config additions are purely additive — no existing tests reference MINIO settings).

- [ ] **Step 5: Commit**

```bash
cd /home/openether/NetDiscoverIT
git add services/api/requirements.txt \
        services/api/app/core/config.py \
        .env.example
git commit -m "feat(storage): add boto3 dependency and MINIO config settings (Group 8a Task 1)"
```

---

## Task 2: MinIO Docker Services

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add MinIO server service to docker-compose.yml**

Open `docker-compose.yml`. Insert the following block after the `# LOCAL AGENT` section (before the `volumes:` declaration at the bottom):

```yaml
  # =============================================================================
  # MINIO (S3-compatible object storage — exports, compliance reports)
  # Console: http://localhost:9001  (login: MINIO_ACCESS_KEY / MINIO_SECRET_KEY)
  # =============================================================================
  minio:
    image: minio/minio:RELEASE.2024-01-16T16-07-38Z
    container_name: netdiscoverit-minio
    restart: unless-stopped
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ACCESS_KEY:-minioadmin}
      MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY:-minioadmin}
    ports:
      - "9000:9000"
      - "9001:9001"
    volumes:
      - minio_data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/ready"]
      interval: 10s
      timeout: 5s
      retries: 5

  # =============================================================================
  # MINIO INIT (one-shot: creates bucket on first start, then exits)
  # =============================================================================
  minio-init:
    image: minio/mc:latest
    depends_on:
      minio:
        condition: service_healthy
    entrypoint: >
      /bin/sh -c "
      mc alias set local http://minio:9000 $${MINIO_ACCESS_KEY:-minioadmin} $${MINIO_SECRET_KEY:-minioadmin} &&
      mc mb --ignore-existing local/$${MINIO_BUCKET:-netdiscoverit} &&
      echo 'Bucket ready.' &&
      exit 0
      "
    restart: "no"
```

- [ ] **Step 2: Add minio_data volume to the volumes section**

In the same `docker-compose.yml`, find the `volumes:` block at the bottom and add `minio_data:`:

```yaml
volumes:
  postgres_data:
  redis_data:
  vault_data:
  ollama_data:
  neo4j_data:
  neo4j_logs:
  agent_data:
  minio_data:
```

- [ ] **Step 3: Add MINIO env vars to the api service**

In `docker-compose.yml`, find the `api:` service `environment:` block. Add these three lines after `- CREDENTIAL_ENCRYPTION_KEY=${CREDENTIAL_ENCRYPTION_KEY}`:

```yaml
      - MINIO_ENDPOINT=http://minio:9000
      - MINIO_ACCESS_KEY=${MINIO_ACCESS_KEY:-minioadmin}
      - MINIO_SECRET_KEY=${MINIO_SECRET_KEY:-minioadmin}
      - MINIO_BUCKET=${MINIO_BUCKET:-netdiscoverit}
```

- [ ] **Step 4: Add minio as a dependency of the api service**

In the `api:` service `depends_on:` block, add:

```yaml
      minio:
        condition: service_healthy
```

- [ ] **Step 5: Verify the stack starts with MinIO**

```bash
cd /home/openether/NetDiscoverIT
docker compose up minio minio-init -d
docker compose logs minio-init
```

Expected output from `minio-init` logs:
```
Bucket ready.
```

Also verify MinIO health:
```bash
curl -f http://localhost:9000/minio/health/ready && echo "MinIO healthy"
```

Expected: `MinIO healthy`

- [ ] **Step 6: Commit**

```bash
cd /home/openether/NetDiscoverIT
git add docker-compose.yml
git commit -m "feat(storage): add MinIO and minio-init Docker services (Group 8a Task 2)"
```

---

## Task 3: Unit Tests — Write Failing Tests

**Files:**
- Create: `services/api/tests/api/test_storage_unit.py`

Write all unit tests before writing the implementation. They must fail with `ModuleNotFoundError` or `ImportError` right now — that's the expected TDD starting state.

- [ ] **Step 1: Create the unit test file**

Create `services/api/tests/api/test_storage_unit.py` with the following content:

```python
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
```

- [ ] **Step 2: Run tests — confirm they fail with ImportError**

```bash
docker exec netdiscoverit-api pytest services/api/tests/api/test_storage_unit.py -v 2>&1 | head -20
```

Expected:
```
ERROR collecting services/api/tests/api/test_storage_unit.py
ImportError: cannot import name 'StorageService' from 'app.services.storage'
```
(or `ModuleNotFoundError` if `storage.py` doesn't exist yet — both are correct)

- [ ] **Step 3: Commit failing tests**

```bash
cd /home/openether/NetDiscoverIT
git add services/api/tests/api/test_storage_unit.py
git commit -m "test(storage): add failing unit tests for StorageService (Group 8a Task 3)"
```

---

## Task 4: StorageService Implementation

**Files:**
- Create: `services/api/app/services/storage.py`

- [ ] **Step 1: Create storage.py**

Create `services/api/app/services/storage.py`:

```python
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
```

- [ ] **Step 2: Run unit tests — confirm they pass**

```bash
docker exec netdiscoverit-api pytest services/api/tests/api/test_storage_unit.py -v
```

Expected output:
```
PASSED test_storage_unit.py::TestUploadFile::test_returns_storage_path_with_correct_format
PASSED test_storage_unit.py::TestUploadFile::test_storage_path_includes_uuid_prefix
PASSED test_storage_unit.py::TestUploadFile::test_calls_put_object_with_correct_args
PASSED test_storage_unit.py::TestUploadFile::test_raises_storage_error_on_client_error
PASSED test_storage_unit.py::TestGeneratePresignedUrl::test_calls_head_object_before_signing
PASSED test_storage_unit.py::TestGeneratePresignedUrl::test_calls_generate_presigned_url_with_correct_params
PASSED test_storage_unit.py::TestGeneratePresignedUrl::test_uses_default_expiry_from_settings
PASSED test_storage_unit.py::TestGeneratePresignedUrl::test_raises_storage_error_when_object_missing
PASSED test_storage_unit.py::TestGeneratePresignedUrl::test_returns_url_string
PASSED test_storage_unit.py::TestDeleteFile::test_calls_delete_object_with_correct_args
PASSED test_storage_unit.py::TestDeleteFile::test_is_noop_for_missing_object
PASSED test_storage_unit.py::TestDeleteFile::test_raises_storage_error_on_unexpected_error

12 passed in ...s
```

If any test fails, read the error message — the most common issues are:
- `patch("app.services.storage.settings")` not working → check the import path matches exactly what's in `storage.py`
- `_client_error("NoSuchKey")` not matching → check the `Code` field spelling in `delete_file`

- [ ] **Step 3: Run full test suite — confirm nothing broken**

```bash
docker exec netdiscoverit-api pytest services/api/tests/ -v --tb=short -q 2>&1 | tail -10
```

Expected: all tests pass, no regressions.

- [ ] **Step 4: Commit**

```bash
cd /home/openether/NetDiscoverIT
git add services/api/app/services/storage.py
git commit -m "feat(storage): add StorageService with upload, presigned URL, and delete (Group 8a Task 4)"
```

---

## Task 5: Integration Tests

**Files:**
- Create: `services/api/tests/api/test_storage_integration.py`

These tests run against the real MinIO container. They are automatically skipped if `MINIO_ENDPOINT` is not in the environment, so the existing test suite in CI (which may not have MinIO running) is unaffected.

- [ ] **Step 1: Create the integration test file**

Create `services/api/tests/api/test_storage_integration.py`:

```python
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

# Isolated test bucket — kept separate from the production 'netdiscoverit' bucket
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
        pass  # bucket already exists — fine
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
```

- [ ] **Step 2: Run integration tests inside the api container**

The api container already has `MINIO_ENDPOINT=http://minio:9000` injected via docker-compose (from Task 2), so MinIO is reachable:

```bash
docker exec netdiscoverit-api \
    pytest services/api/tests/api/test_storage_integration.py -v
```

Expected:
```
PASSED test_storage_integration.py::TestStorageIntegration::test_upload_and_retrieve
PASSED test_storage_integration.py::TestStorageIntegration::test_delete_removes_object

2 passed in ...s
```

If MinIO is not running:
```bash
cd /home/openether/NetDiscoverIT && docker compose up minio minio-init -d
# wait ~15s for health check, then retry
```

- [ ] **Step 3: Confirm unit tests still skip cleanly without MINIO_ENDPOINT**

Run the full suite from the host (no MINIO env vars set):

```bash
docker exec netdiscoverit-api pytest services/api/tests/ -v --tb=short -q 2>&1 | grep -E "passed|skipped|failed|error"
```

Expected: integration tests show as `SKIPPED`, all others pass.

- [ ] **Step 4: Commit**

```bash
cd /home/openether/NetDiscoverIT
git add services/api/tests/api/test_storage_integration.py
git commit -m "test(storage): add integration tests for StorageService (Group 8a Task 5)"
```

---

## Post-Implementation Checklist

After all 5 tasks are complete:

- [ ] `make up` starts all services including MinIO without errors
- [ ] MinIO console accessible at `http://localhost:9001` (login: `minioadmin` / `minioadmin`)
- [ ] `netdiscoverit` bucket exists in the console
- [ ] All 12 unit tests pass
- [ ] Both integration tests pass inside the api container
- [ ] Full test suite shows no regressions
- [ ] Update `claw-memory` (`/tmp/claw-memory/TODO.md` and `current-state.md`) — mark Group 8a complete
- [ ] Push all commits to `main`
