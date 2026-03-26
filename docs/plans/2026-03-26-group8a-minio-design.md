# Group 8a — MinIO Object Storage — Design Spec

**Date:** 2026-03-26
**Status:** Approved
**Depends on:** Group 7 (NLI/RAG) — complete
**Required by:** Group 8b (Compliance Report Generation)

---

## Purpose

NetDiscoverIT generates large binary exports — compliance reports (PDF/DOCX), topology diagrams (Drawio/Visio), and audit packages. These files cannot be stored in PostgreSQL (wrong tool) or on the container's local filesystem (ephemeral, lost on restart). MinIO provides durable, S3-compatible object storage running as a Docker service alongside the rest of the stack.

The `ExportDocument` PostgreSQL model already exists and is designed around this: it stores the MinIO `storage_path` and metadata, not the file bytes themselves.

**Privacy invariant — unchanged:** MinIO stores only generated *output* files (reports, diagrams). Raw device configs, sanitized configs, and config text of any kind are never written to MinIO. This is consistent with the existing architecture decision that no config text ever leaves the customer network.

---

## Scope

Group 8a is pure infrastructure and client plumbing. No business logic, no report generation. It enables Group 8b to call `storage.upload_file()` and `storage.generate_presigned_url()` without knowing anything about MinIO internals.

**In scope:**
- MinIO Docker service + bucket initialisation
- Environment variable additions to config + `.env.example`
- `StorageService` wrapper with three methods
- Unit tests (mocked) + integration test (live MinIO)

**Out of scope:**
- Compliance report generation (Group 8b)
- Export format rendering (Group 8c — deprioritised)
- File expiry enforcement / lifecycle cleanup (Group 8b concern)

---

## Architecture

### New Docker Service

MinIO runs as two containers:

| Container | Purpose |
|-----------|---------|
| `minio` | S3-compatible object storage server (port 9000 API, 9001 console) |
| `minio-init` | One-shot init: creates the `netdiscoverit` bucket, then exits |

The `minio-init` container uses the MinIO Client (`mc`) to create the bucket idempotently on first start. This avoids any application-level bucket-creation logic at API startup.

Data persists in a named Docker volume: `minio_data`.

### SDK Choice: boto3 (S3-compatible mode)

`boto3` is used with `endpoint_url` pointing to MinIO. This makes the storage layer fully vendor-agnostic — switching to AWS S3, Cloudflare R2, or any S3-compatible provider requires only env var changes, zero code changes.

```
Development:  endpoint_url = http://minio:9000   (Docker service name)
Production:   endpoint_url = https://s3.amazonaws.com  (or any S3-compatible)
```

### StorageService Location

```
services/api/app/services/storage.py
```

Follows the existing services pattern (alongside `alert_routing.py`, `change_service.py`, etc.). Instantiated once as a module-level singleton, imported wherever needed.

---

## Components

### `StorageService`

```python
class StorageService:
    def upload_file(
        self,
        org_id: str,
        filename: str,
        data: bytes,
        content_type: str,
    ) -> str:
        """
        Upload file bytes to MinIO.
        Returns storage_path: "exports/{org_id}/{uuid4}-{filename}"
        Raises StorageError on failure.
        """

    def generate_presigned_url(
        self,
        storage_path: str,
        expires_seconds: int | None = None,
    ) -> str:
        """
        Generate a time-limited presigned GET URL for the given storage_path.
        expires_seconds defaults to settings.MINIO_PRESIGNED_EXPIRY_SECONDS (3600).
        Calls head_object first to verify existence — raises StorageError immediately
        if the object is missing, rather than returning a URL that 404s at download time.
        """

    def delete_file(self, storage_path: str) -> None:
        """
        Delete object at storage_path. No-op if object does not exist.
        Raises StorageError on unexpected failure.
        """
```

**Key design decisions:**
- `storage_path` format: `exports/{org_id}/{uuid4}-{filename}` — org-scoped, UUID-prefixed to prevent collisions, human-readable suffix
- `StorageError` is a custom exception defined in `storage.py`; all boto3 `ClientError` instances are caught and re-raised as `StorageError` — no boto3 types leak into callers
- Bucket creation is handled by the `minio-init` Docker container, not by `StorageService.__init__`; the service assumes the bucket exists
- The boto3 client is created once in `__init__` and reused — thread-safe for read operations, safe for Celery workers

### `StorageError`

Custom exception class. Carries `message` and optional `original_error` (the underlying `ClientError`). Celery workers catch this, set `ExportDocument.status = "failed"`, and log the `original_error`.

---

## Data Flows

### Upload Flow (Celery Worker → MinIO)

```
Celery task generates file bytes (PDF, DOCX, etc.)
  → storage.upload_file(org_id, filename, data, content_type)
  → boto3.put_object(Bucket=bucket, Key=storage_path, Body=data, ContentType=content_type)
  → Returns storage_path
  → Worker writes: ExportDocument.storage_path = storage_path
                   ExportDocument.status = "completed"
                   ExportDocument.file_size_bytes = len(data)
                   ExportDocument.completed_at = now()
```

### Download Flow (API Route → Frontend)

```
GET /api/v1/compliance/reports/{id}   (Group 8b route)
  → Load ExportDocument, verify org ownership
  → Assert status == "completed"
  → storage.generate_presigned_url(storage_path, expires_seconds=3600)
  → boto3.generate_presigned_url("get_object", ...)
  → Response includes: { "download_url": "<presigned>", "expires_in": 3600 }
  → Frontend redirects user directly to MinIO — file never proxied through API server
```

### Delete Flow (Expiry Cleanup — future Celery beat task)

```
Celery beat scans ExportDocument where expires_at < now() and status = "completed"
  → storage.delete_file(storage_path)
  → ExportDocument.status = "deleted" (or hard delete row)
```
*Note: The delete Celery task is out of scope for Group 8a but the `delete_file()` method must exist.*

---

## Environment Variables

Five new settings added to `config.py` and `.env.example`:

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `MINIO_ENDPOINT` | `http://minio:9000` | No | MinIO server URL |
| `MINIO_ACCESS_KEY` | — | **Yes** | Access key (no default, fails loudly) |
| `MINIO_SECRET_KEY` | — | **Yes** | Secret key (no default, fails loudly) |
| `MINIO_BUCKET` | `netdiscoverit` | No | Target bucket name |
| `MINIO_PRESIGNED_EXPIRY_SECONDS` | `3600` | No | Presigned URL lifetime (1 hour) |

`MINIO_ACCESS_KEY` and `MINIO_SECRET_KEY` follow the same no-default pattern as `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, etc. — the app fails at startup with a clear error if unset.

The docker-compose `minio` service sets these from `.env` and also passes them to `minio-init` for bucket creation.

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| MinIO unreachable at API startup | App starts normally — storage is non-critical for API health check |
| Upload fails (MinIO down, timeout) | `StorageError` raised; Celery worker sets `ExportDocument.status="failed"`, `error_message` populated |
| Presigned URL for non-existent object | `StorageError` raised; API route returns HTTP 404 |
| Bucket does not exist | `StorageError` raised with clear message; should not happen if `minio-init` ran correctly |
| boto3 `ClientError` | Always caught in `StorageService`; logged with full detail; re-raised as `StorageError` |

No silent failures. All errors are logged at `ERROR` level with the original exception attached.

---

## Testing

### Unit Tests — `services/api/tests/api/test_storage_unit.py`

All boto3 calls mocked with `unittest.mock`. No MinIO server needed. Tests:

- `test_upload_file_returns_correct_storage_path` — verifies path format `exports/{org_id}/{uuid}-{filename}`
- `test_upload_file_calls_put_object_with_correct_args` — verifies bucket, key, body, content_type
- `test_upload_file_raises_storage_error_on_client_error` — boto3 raises `ClientError`, must become `StorageError`
- `test_generate_presigned_url_calls_head_object_first` — verifies existence check before signing
- `test_generate_presigned_url_calls_correct_params` — verifies method, key, expiry
- `test_generate_presigned_url_uses_default_expiry` — default from settings
- `test_generate_presigned_url_raises_storage_error_on_client_error`
- `test_delete_file_calls_delete_object` — verifies key and bucket
- `test_delete_file_is_noop_for_missing_object` — `NoSuchKey` → no exception raised
- `test_delete_file_raises_storage_error_on_unexpected_error`
- `test_storage_path_includes_uuid_prefix` — two uploads of same filename produce different paths

### Integration Test — `services/api/tests/api/test_storage_integration.py`

Uses real MinIO. Skipped if `MINIO_ENDPOINT` is not set (CI environments without MinIO skip gracefully).

- `test_upload_and_retrieve` — upload bytes, generate presigned URL, HTTP GET the URL, verify bytes match
- `test_delete_removes_object` — upload, delete, confirm presigned URL returns 404
- `test_presigned_url_expires` — (optional, difficult to test precisely; may be omitted in favour of unit coverage)

---

## File Map

| Action | Path |
|--------|------|
| Create | `services/api/app/services/storage.py` |
| Create | `services/api/tests/api/test_storage_unit.py` |
| Create | `services/api/tests/api/test_storage_integration.py` |
| Modify | `docker-compose.yml` — add `minio` + `minio-init` services + `minio_data` volume |
| Modify | `services/api/requirements.txt` — add `boto3>=1.34.0` |
| Modify | `services/api/app/core/config.py` — add 5 MINIO_* settings |
| Modify | `.env.example` — add MINIO_* vars with comments |

---

## Dependencies

- `boto3>=1.34.0` — S3-compatible client
- MinIO Docker image: `minio/minio:RELEASE.2024-01-16T16-07-38Z` (pinned release for reproducibility)
- MinIO Client image: `minio/mc:latest` (init container only)

No new Python dependencies beyond boto3. `botocore` is a boto3 subdependency and comes automatically.
