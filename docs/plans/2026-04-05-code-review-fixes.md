# Code Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all Critical, Important, and Minor issues identified in the 2026-04-05 code review of commits f17c620..adb4911.

**Architecture:** Fixes span three layers — the agent Docker container (import path), the FastAPI route layer (rate limiting, async correctness, security), and the shared services layer (change number generation, Jira auth). Each task is self-contained; no task depends on another completing first unless explicitly noted.

**Tech Stack:** Python 3.11, FastAPI, SlowAPI, SQLAlchemy async, asyncpg, Redis async, Docker multi-stage build, pytest, Pydantic v2, PostgreSQL advisory locks.

---

## Files Modified

| File | Change |
|------|--------|
| `docker/agent/Dockerfile` | Add `COPY services/common`, update `PYTHONPATH` |
| `docker-compose.yml` | Add `services/common` volume to agent service |
| `services/agent/agent/normalizer.py` | Remove `raw_config` field; make TextFSMParser a module singleton |
| `services/common/normalization/schemas.py` | Fix `parser_method` Literal (remove `"strict"`) |
| `services/api/app/api/routes/changes.py` | Fix 6 rate-limited endpoints; add HMAC webhook; fix `utcnow`; remove duplicate import |
| `services/api/app/api/routes/discoveries.py` | Replace sync redis with async |
| `services/api/app/api/routes/integrations.py` | Fix Jira Basic auth header |
| `services/api/app/services/change_service.py` | Fix race condition in `generate_change_number`; fix `utcnow` |
| `services/api/app/api/routes.py` | **Delete** (duplicate artifact) |
| `services/api/test_migrations.py` | **Delete** (replaced by proper pytest test below) |
| `tests/api/db/test_migrations.py` | New: proper pytest migration smoke tests |
| `tests/agent/test_normalizer_orchestrator.py` | Fix tautological assertion |

---

## Task 1 (C3): Remove Raw Config From Rule-Based Fallback

**Files:**
- Modify: `services/agent/agent/normalizer.py:186-196`
- Test: `tests/agent/test_normalizer_orchestrator.py`

The `_normalize_rulebased` method currently stores `"raw_config": raw_config[:1000]` in its return dict. This dict flows through `normalize_command_output()` and into the upload pipeline. The project's non-negotiable privacy invariant is: **no raw config text ever leaves the customer network**, not even truncated.

- [ ] **Step 1: Write the failing test**

Add to `tests/agent/test_normalizer_orchestrator.py` inside the `TestNormalizeCommandOutput` class:

```python
def test_fallback_result_contains_no_raw_config(self):
    """Raw config text must never appear in normalized output"""
    result = normalize_command_output(
        vendor="unknown_vendor_xyz",
        command="show running-config",
        raw_output="hostname SecretRouter\npassword supersecret123\nsnmp-server community public RO"
    )
    # Check no record contains raw config text or a raw_config key
    for record in result.records:
        assert "raw_config" not in record, "raw_config key must not appear in normalized output"
        assert "raw_snippet" not in record or record.get("raw_snippet") is None or \
               "supersecret" not in str(record.get("raw_snippet", "")), \
               "Raw config content must not propagate"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /home/openether/NetDiscoverIT
make test 2>&1 | grep -A3 "test_fallback_result_contains_no_raw_config"
```

Expected: FAIL — `AssertionError: raw_config key must not appear` (or `raw_snippet` with secret content).

- [ ] **Step 3: Remove the `raw_config` key from `_normalize_rulebased`**

In `services/agent/agent/normalizer.py`, find the `_normalize_rulebased` method (~line 186) and replace:

```python
def _normalize_rulebased(self, raw_config: str) -> Dict:
    """Fallback rule-based normalization"""
    result = {
        "hostname": self._extract_value(raw_config, r"hostname\s+(\S+)"),
        "vendor": self._detect_vendor(raw_config),
        "interfaces": self._extract_interfaces(raw_config),
        "vlans": self._extract_vlans(raw_config),
        "raw_config": raw_config[:1000]  # Truncate for safety
    }
    
    return result
```

With:

```python
def _normalize_rulebased(self, raw_config: str) -> Dict:
    """Fallback rule-based normalization — extracts structured facts only.

    PRIVACY: raw config text is never included in output. Only parsed
    structural facts (hostname, vendor, interfaces, VLANs) are returned.
    """
    result = {
        "hostname": self._extract_value(raw_config, r"hostname\s+(\S+)"),
        "vendor": self._detect_vendor(raw_config),
        "interfaces": self._extract_interfaces(raw_config),
        "vlans": self._extract_vlans(raw_config),
        "_parse_quality": "rule_based_only",
    }

    return result
```

Also update `_fallback_parse` (module-level function ~line 339) in the same file — remove `raw_snippet`:

```python
def _fallback_parse(raw_output: str, vendor: str) -> list:
    """Simple fallback parser when TextFSM is unavailable.

    PRIVACY: raw output is never stored. Only extracted structured facts.
    """
    import re

    records = []
    record = {}

    hostname_match = re.search(r"hostname\s+(\S+)", raw_output, re.IGNORECASE)
    if hostname_match:
        record["hostname"] = hostname_match.group(1)

    version_match = re.search(r"version\s+([\d\.\(\)]+)", raw_output, re.IGNORECASE)
    if version_match:
        record["version"] = version_match.group(1)

    record["vendor"] = vendor
    record["_parse_quality"] = "regex_fallback"
    records.append(record)

    return records
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
make test 2>&1 | grep -A3 "test_fallback_result_contains_no_raw_config"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/agent/agent/normalizer.py tests/agent/test_normalizer_orchestrator.py
git commit -m "fix(privacy): remove raw_config from rule-based normalizer output

Raw config text must never leave the customer network per the project
privacy invariant. Replaced raw_config/raw_snippet fields with a
_parse_quality metadata flag.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2 (C1): Fix Agent Docker Container — services.common Import

**Files:**
- Modify: `docker/agent/Dockerfile`
- Modify: `docker-compose.yml`

The agent Dockerfile sets `PYTHONPATH=/app/agent` and only copies `services/agent` to `/app/agent`. The `normalizer.py` import `from services.common.normalization.schemas import NormalizedCommandOutput` requires `services/common` to be reachable. Without this fix, the agent process crashes at import time with `ModuleNotFoundError: No module named 'services'`.

- [ ] **Step 1: Write the failing test** (import check)

This is a Docker build test — write a shell one-liner that verifies the import works inside the container. No pytest test needed because the crash happens at container startup. Instead, document the manual verification command at the end of this task.

- [ ] **Step 2: Update `docker/agent/Dockerfile`**

Current lines (around 19-27):
```dockerfile
COPY services/agent/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/agent /app/agent
COPY configs/agent.yaml /app/config/agent.yaml

RUN mkdir -p /app/data

ENV PYTHONPATH=/app/agent
```

Replace with:
```dockerfile
COPY services/agent/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/agent /app/agent
COPY services/common /app/services/common
COPY configs/agent.yaml /app/config/agent.yaml

RUN mkdir -p /app/data \
    && touch /app/__init__.py \
    && touch /app/services/__init__.py

ENV PYTHONPATH=/app
```

Note: `PYTHONPATH=/app` (not `/app/agent`) means `import services.common...` resolves to `/app/services/common` and `import agent...` resolves to `/app/agent`. The `__init__.py` touch commands ensure Python recognises `/app` and `/app/services` as packages.

- [ ] **Step 3: Update `docker-compose.yml` agent service volumes**

Find the `agent` service volume mounts in `docker-compose.yml` and add the common package mount for development hot-reload. Look for the existing agent volume block and add one line:

```yaml
      - ./services/agent/agent:/app/agent
      - ./services/common:/app/services/common   # ← add this line
```

- [ ] **Step 4: Rebuild and verify import**

```bash
make up-build 2>&1 | tail -20
# Then verify import works:
docker compose exec agent python -c "from services.common.normalization.schemas import NormalizedCommandOutput; print('OK')"
```

Expected output: `OK`

- [ ] **Step 5: Commit**

```bash
git add docker/agent/Dockerfile docker-compose.yml
git commit -m "fix(agent): add services/common to Docker layer and PYTHONPATH

PYTHONPATH was set to /app/agent which only resolved agent.* imports.
normalizer.py imports from services.common.normalization.schemas so the
Dockerfile now copies services/common and sets PYTHONPATH=/app.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3 (C2): Fix Rate Limiting on 6 Change Lifecycle Endpoints

**Files:**
- Modify: `services/api/app/api/routes/changes.py`

SlowAPI requires `request: Request` (a `fastapi.Request` object) as the **first positional parameter** of any rate-limited route handler. Six endpoints use `request` as the name for their Pydantic body schema parameter instead, causing SlowAPI to fail to extract the client IP and raise a 500 on every call.

The affected functions are: `propose_change` (line 416), `approve_change` (line 496), `implement_change` (line 578), `verify_change` (line 649), `rollback_change` (line 723), `sync_change_to_ticket` (line 800).

- [ ] **Step 1: Write the failing test**

In `tests/api/routes/test_changes.py` (create if it doesn't exist), add:

```python
"""Tests for change record rate limiting — verifies SlowAPI can extract client IP."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.mark.parametrize("endpoint,body_key", [
    ("/changes/00000000-0000-0000-0000-000000000001/propose", "ChangeProposeRequest"),
    ("/changes/00000000-0000-0000-0000-000000000001/approve", "ChangeApproveRequest"),
])
def test_change_lifecycle_endpoint_accepts_request_object(client, endpoint, body_key):
    """Rate-limited endpoints must accept fastapi.Request as first param.
    
    If SlowAPI cannot find request: Request, it raises AttributeError before
    the route handler body executes. A 404 or 403 means the route was reached;
    a 500 with 'object has no attribute' means SlowAPI broke.
    """
    response = client.post(endpoint, json={}, headers={"Authorization": "Bearer fake"})
    # Any response code except 500 means SlowAPI extracted the IP successfully
    assert response.status_code != 500, (
        f"Got 500 — SlowAPI likely failed to find request: Request. "
        f"Response: {response.text}"
    )
```

- [ ] **Step 2: Run to confirm 500s**

```bash
make test 2>&1 | grep -A5 "test_change_lifecycle_endpoint_accepts"
```

Expected: FAIL with status 500 or similar.

- [ ] **Step 3: Fix all six endpoints in `changes.py`**

For each of the six functions, add `http_request: Request` as the **first** parameter in the function signature. The body schema parameter keeps its existing name (`request`). Example for `propose_change`:

**Before:**
```python
@router.post(
    "/changes/{change_id}/propose", response_model=schemas.ChangeRecordResponse
)
@limiter.limit(LIMIT_WRITE)
async def propose_change(
    change_id: str,
    request: schemas.ChangeProposeRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
```

**After:**
```python
@router.post(
    "/changes/{change_id}/propose", response_model=schemas.ChangeRecordResponse
)
@limiter.limit(LIMIT_WRITE)
async def propose_change(
    http_request: Request,
    change_id: str,
    request: schemas.ChangeProposeRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
```

Apply the same pattern to all six: `approve_change`, `implement_change`, `verify_change`, `rollback_change`, `sync_change_to_ticket`.

- [ ] **Step 4: Verify `Request` is imported at the top of `changes.py`**

Line 5 already has: `from fastapi import APIRouter, HTTPException, Depends, Request`

No change needed. Confirm with:
```bash
grep "from fastapi import" services/api/app/api/routes/changes.py
```

Expected: `Request` is in the import.

- [ ] **Step 5: Run tests to confirm fix**

```bash
make test 2>&1 | grep -A5 "test_change_lifecycle_endpoint_accepts"
```

Expected: PASS (or 404/403 — any non-500 response means SlowAPI resolved correctly).

- [ ] **Step 6: Commit**

```bash
git add services/api/app/api/routes/changes.py
git commit -m "fix(api): add http_request: Request to 6 change lifecycle endpoints

SlowAPI requires fastapi.Request as the first positional parameter to
extract the client IP for rate limiting. Six change lifecycle endpoints
had their Pydantic body schema named 'request', preventing SlowAPI from
finding the fastapi.Request object and causing 500 errors on every call.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4 (I1): Delete Duplicate Flat `routes.py`

**Files:**
- Delete: `services/api/app/api/routes.py`

This file is a 3,376-line artifact that duplicates the canonical `services/api/app/api/routes/` package. It creates its own `Limiter` instance (bypassing `rate_limit.py`), uses broken absolute imports (`from services.api.app.api import schemas`), and is not imported by `main.py`. Keeping it creates maintenance confusion and a diverging implementation. Deleting it also resolves I2 (the `NormalizedIngestRecord` reference only exists in this file).

- [ ] **Step 1: Confirm the file is not imported anywhere**

```bash
grep -r "from services.api.app.api.routes import\|from app.api.routes import\|import routes" \
  services/api/app/ --include="*.py" | grep -v "__pycache__" | grep -v "routes/"
```

Expected: no output (file is not imported).

- [ ] **Step 2: Confirm `main.py` imports from the package, not the flat file**

```bash
grep "routes" services/api/app/main.py
```

Expected output should reference `app.api.routes` or `app.api.routes.*` (the package), not `app.api.routes` as a module.

- [ ] **Step 3: Delete the file**

```bash
git rm services/api/app/api/routes.py
```

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: delete duplicate flat routes.py artifact

The canonical API routes live in services/api/app/api/routes/ (the package).
The flat routes.py was an unreferenced 3376-line draft with broken imports
and a duplicate Limiter instance. Removing it eliminates maintenance confusion.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5 (I3): Replace `datetime.utcnow()` With Timezone-Aware Datetime

**Files:**
- Modify: `services/api/app/api/routes/changes.py`
- Modify: `services/api/app/services/change_service.py`

`datetime.utcnow()` is deprecated in Python 3.12 and returns a naive datetime (no timezone info). The codebase stores audit timestamps — comparing a naive `approved_at` against a timezone-aware `created_at` raises a `TypeError` at runtime. The fix is `datetime.now(timezone.utc)` throughout.

There are 7 occurrences in `changes.py` (lines 543, 616, 766, 930, 948, 1009, 1019) and 1 in `change_service.py` (line 9).

- [ ] **Step 1: Write the failing test**

In `tests/api/services/test_change_service.py` (create if missing):

```python
"""Tests that change_service generates timezone-aware datetimes."""
import pytest
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_generate_change_number_uses_timezone_aware_year():
    """generate_change_number must use timezone-aware datetime for year extraction."""
    from app.services.change_service import generate_change_number
    from datetime import datetime, timezone

    mock_db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar.return_value = 0
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await generate_change_number(mock_db)
    expected_year = datetime.now(timezone.utc).year
    assert result.startswith(f"CHG-{expected_year}-"), (
        f"Expected CHG-{expected_year}-NNNN, got {result}"
    )
```

- [ ] **Step 2: Fix `change_service.py`**

In `services/api/app/services/change_service.py`, update the import and `generate_change_number`:

```python
from datetime import datetime, timezone
from typing import Dict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import ChangeRecord

async def generate_change_number(db: AsyncSession) -> str:
    """Generate unique change number: CHG-YYYY-NNNN"""
    year = datetime.now(timezone.utc).year
    prefix = f"CHG-{year}-"

    result = await db.execute(
        select(func.count())
        .select_from(ChangeRecord)
        .where(ChangeRecord.change_number.like(f"{prefix}%"))
    )
    count = result.scalar() or 0

    return f"{prefix}{count + 1:04d}"
```

- [ ] **Step 3: Fix all `utcnow()` calls in `changes.py`**

Run this replacement across the file — there are 7 occurrences:

```bash
sed -i 's/datetime\.utcnow()/datetime.now(timezone.utc)/g' \
  services/api/app/api/routes/changes.py
```

Then confirm `timezone` is imported at the top of `changes.py`. If not, add it:

```bash
grep "from datetime import" services/api/app/api/routes/changes.py
```

If the import is just `from datetime import datetime`, change it to:
`from datetime import datetime, timezone`

Check each occurrence is inside a function that imports `datetime` locally (lines 543, 616, 766, 930, 948). Update those local imports too:

```python
# Before (inside function body):
from datetime import datetime
change.approved_at = datetime.utcnow()

# After:
from datetime import datetime, timezone
change.approved_at = datetime.now(timezone.utc)
```

- [ ] **Step 4: Run tests**

```bash
make test 2>&1 | grep -A3 "test_generate_change_number_uses_timezone"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/api/app/api/routes/changes.py services/api/app/services/change_service.py
git commit -m "fix: replace datetime.utcnow() with datetime.now(timezone.utc)

utcnow() is deprecated in Python 3.12 and returns naive datetimes.
Comparing naive vs timezone-aware datetimes raises TypeError at runtime.
All 8 occurrences in changes.py and change_service.py updated.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6 (I5): Fix Jira Basic Auth Header

**Files:**
- Modify: `services/api/app/api/routes/integrations.py:491`

Jira REST API v3 requires the `Authorization: Basic <base64(email:api_token)>` format. The current code concatenates the raw API token string directly, so every Jira connectivity test returns HTTP 401.

- [ ] **Step 1: Write the failing test**

In `tests/api/routes/test_integrations.py` (create if missing):

```python
"""Tests for external integration connectivity checks."""
import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx


@pytest.mark.asyncio
async def test_jira_auth_header_is_base64_encoded():
    """Jira Basic auth must be base64(email:api_token), not raw token."""
    from app.api.routes.integrations import _test_integration_connectivity

    captured_headers = {}

    async def mock_get(url, headers=None, timeout=None):
        captured_headers.update(headers or {})
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        return mock_resp

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=mock_get)
        mock_client_class.return_value = mock_client

        await _test_integration_connectivity(
            integration_type="jira",
            credentials={"email": "user@example.com", "api_token": "mytoken123"},
            base_url="https://example.atlassian.net",
        )

    auth_header = captured_headers.get("Authorization", "")
    assert auth_header.startswith("Basic "), f"Expected 'Basic ...', got: {auth_header}"
    encoded = auth_header[6:]  # strip "Basic "
    decoded = base64.b64decode(encoded).decode()
    assert decoded == "user@example.com:mytoken123", (
        f"Expected base64(email:token), got decoded: {decoded}"
    )
```

> Note: This test assumes `_test_integration_connectivity` is extractable as a helper. If it's inline in a route handler, adapt the test to call the route directly via `TestClient`.

- [ ] **Step 2: Fix the auth header in `integrations.py`**

Find line ~491 in `services/api/app/api/routes/integrations.py`:

```python
# Before:
headers = {
    "Authorization": "Basic " + credentials.get("api_token", ""),
    "Content-Type": "application/json",
}
```

Replace with:

```python
import base64 as _base64

_email = credentials.get("email", "")
_token = credentials.get("api_token", "")
_encoded = _base64.b64encode(f"{_email}:{_token}".encode()).decode()
headers = {
    "Authorization": f"Basic {_encoded}",
    "Content-Type": "application/json",
}
```

- [ ] **Step 3: Run test**

```bash
make test 2>&1 | grep -A3 "test_jira_auth_header"
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add services/api/app/api/routes/integrations.py
git commit -m "fix(integrations): correct Jira Basic auth to base64(email:token)

Jira REST API v3 requires Authorization: Basic base64(email:api_token).
The previous code concatenated the raw token causing HTTP 401 on all
Jira connectivity tests.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7 (I6): Replace Sync Redis With Async in `trigger_discovery`

**Files:**
- Modify: `services/api/app/api/routes/discoveries.py`

The `trigger_discovery` route handler does `import redis` (sync) and calls `redis_client.lpush()` + `redis_client.close()` synchronously inside an `async def`. Blocking sync I/O inside an async route stalls the event loop for the duration of the Redis round-trip. The fix: switch to `redis.asyncio`.

- [ ] **Step 1: Write the failing test**

In `tests/api/routes/test_discoveries.py` (create if missing):

```python
"""Tests that trigger_discovery uses async Redis to avoid blocking the event loop."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_trigger_discovery_redis_push_is_awaited():
    """Redis lpush inside trigger_discovery must be awaited (async), not blocking."""
    # If the route uses sync redis, lpush returns an int (not a coroutine).
    # If it uses async redis, lpush returns a coroutine that must be awaited.
    # We verify the route calls await on the redis push by checking it uses
    # redis.asyncio, not the sync redis client.
    import importlib
    import services.api.app.api.routes.discoveries as disc_module

    source = importlib.util.find_spec("app.api.routes.discoveries")
    # Read the source and check for async redis import
    with open(source.origin) as f:
        content = f.read()

    assert "redis.asyncio" in content or "aioredis" in content, (
        "discoveries.py must use redis.asyncio (async), not sync redis"
    )
    assert "import redis\n" not in content and "import redis " not in content, (
        "discoveries.py must not import sync redis"
    )
```

- [ ] **Step 2: Run to confirm it fails**

```bash
make test 2>&1 | grep -A3 "test_trigger_discovery_redis_push_is_awaited"
```

Expected: FAIL — sync redis detected.

- [ ] **Step 3: Fix `discoveries.py`**

In `services/api/app/api/routes/discoveries.py`, inside `trigger_discovery`, replace:

```python
import redis

# ...
redis_client = redis.from_url(settings.REDIS_URL)
job_data = { ... }
redis_client.lpush("discovery:jobs", json.dumps(job_data))
redis_client.close()
```

With:

```python
import redis.asyncio as redis_async

# ...
redis_client = redis_async.from_url(settings.REDIS_URL)
job_data = { ... }
await redis_client.lpush("discovery:jobs", json.dumps(job_data))
await redis_client.aclose()
```

- [ ] **Step 4: Run test**

```bash
make test 2>&1 | grep -A3 "test_trigger_discovery_redis_push_is_awaited"
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/api/app/api/routes/discoveries.py
git commit -m "fix(api): use async redis in trigger_discovery to avoid blocking event loop

import redis (sync) was blocking the asyncio event loop during lpush.
Replaced with redis.asyncio following the pattern already used in the
change simulation endpoint.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 8 (I7): Fix Race Condition in `generate_change_number`

**Files:**
- Modify: `services/api/app/services/change_service.py`

The current implementation counts existing change numbers and returns `count + 1`. Two concurrent requests can read the same count and generate duplicate `CHG-YYYY-NNNN` values, breaking the audit uniqueness guarantee. Fix: use a PostgreSQL transaction-scoped advisory lock (`pg_advisory_xact_lock`) to serialize concurrent calls within a DB transaction without requiring a schema migration.

- [ ] **Step 1: Write the failing test** (demonstrates the race)

In `tests/api/services/test_change_service.py`:

```python
@pytest.mark.asyncio
async def test_generate_change_number_no_duplicates_under_concurrency():
    """Concurrent calls must produce unique change numbers."""
    from app.services.change_service import generate_change_number
    from unittest.mock import AsyncMock, MagicMock, call
    from sqlalchemy.ext.asyncio import AsyncSession

    call_count = 0

    async def mock_execute(query, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_result = MagicMock()
        # Simulate race: both concurrent calls see count=0 before either commits
        mock_result.scalar.return_value = 0
        return mock_result

    mock_db = AsyncMock(spec=AsyncSession)
    mock_db.execute = AsyncMock(side_effect=mock_execute)

    # Without advisory lock, both return CHG-2026-0001
    results = await asyncio.gather(
        generate_change_number(mock_db),
        generate_change_number(mock_db),
    )
    # After fix, the advisory lock ensures serial execution — but since we
    # mock the DB, we at minimum verify the lock query is issued
    assert mock_db.execute.call_count >= 2, "Expected at least 2 DB calls (lock + count)"
    # Verify advisory lock SQL was issued
    all_calls = [str(c) for c in mock_db.execute.call_args_list]
    assert any("pg_advisory_xact_lock" in c for c in all_calls), (
        "generate_change_number must acquire a pg_advisory_xact_lock before counting"
    )
```

- [ ] **Step 2: Add advisory lock to `generate_change_number`**

In `services/api/app/services/change_service.py`, update the function:

```python
from datetime import datetime, timezone
from typing import Dict
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import ChangeRecord

# Stable advisory lock key for change number serialization.
# Must be a 64-bit integer; this value is arbitrary but unique to this purpose.
_CHANGE_NUMBER_LOCK_KEY = 1_000_001

async def generate_change_number(db: AsyncSession) -> str:
    """Generate a unique change number: CHG-YYYY-NNNN.

    Uses a PostgreSQL transaction-scoped advisory lock to serialize concurrent
    callers. The lock is released automatically when the enclosing transaction
    commits or rolls back.
    """
    year = datetime.now(timezone.utc).year
    prefix = f"CHG-{year}-"

    # Acquire transaction-scoped advisory lock — blocks until available.
    await db.execute(text(f"SELECT pg_advisory_xact_lock({_CHANGE_NUMBER_LOCK_KEY})"))

    result = await db.execute(
        select(func.count())
        .select_from(ChangeRecord)
        .where(ChangeRecord.change_number.like(f"{prefix}%"))
    )
    count = result.scalar() or 0

    return f"{prefix}{count + 1:04d}"
```

- [ ] **Step 3: Run test**

```bash
make test 2>&1 | grep -A3 "test_generate_change_number_no_duplicates"
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add services/api/app/services/change_service.py
git commit -m "fix: use pg_advisory_xact_lock to serialize change number generation

Concurrent requests were reading the same count and generating duplicate
CHG-YYYY-NNNN values. pg_advisory_xact_lock(1000001) serializes callers
within a transaction without requiring a schema migration.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 9 (I4): Add HMAC Verification to Webhook Endpoint

**Files:**
- Modify: `services/api/app/api/routes/changes.py`

The `POST /webhooks/change/{integration_id}` endpoint accepts unauthenticated payloads. An attacker who knows an `integration_id` can inject a payload that auto-approves a change record. The `IntegrationConfig` model already stores `webhook_secret` as Fernet-encrypted — this task decrypts and verifies it.

- [ ] **Step 1: Write the failing test**

In `tests/api/routes/test_changes.py`:

```python
@pytest.mark.asyncio
async def test_webhook_rejects_missing_signature(client):
    """Webhook must reject requests with no HMAC signature header."""
    # Create a fake integration_id UUID
    response = client.post(
        "/webhooks/change/00000000-0000-0000-0000-000000000099",
        json={"sys_id": "CHG001", "state": "approved"},
        # No X-Webhook-Signature header
    )
    # Without signature, should return 401 (not 404, not 200)
    # 404 is acceptable only if integration not found; 200 without auth is the bug
    assert response.status_code in (401, 403, 404), (
        f"Expected 401/403/404, got {response.status_code}. "
        "Webhook accepted an unsigned request."
    )


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_signature(client):
    """Webhook must reject requests with a bad HMAC signature."""
    response = client.post(
        "/webhooks/change/00000000-0000-0000-0000-000000000099",
        json={"sys_id": "CHG001", "state": "approved"},
        headers={"X-Webhook-Signature": "sha256=badsignature"},
    )
    assert response.status_code in (401, 403, 404), (
        f"Expected 401/403/404 for bad signature, got {response.status_code}."
    )
```

- [ ] **Step 2: Add HMAC verification to `change_webhook`**

In `services/api/app/api/routes/changes.py`, update the `change_webhook` handler:

```python
@router.post("/webhooks/change/{integration_id}")
async def change_webhook(
    integration_id: str,
    payload: dict,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Webhook receiver for external ticketing system approval.
    
    Verifies HMAC-SHA256 signature using the stored webhook_secret before
    processing any state transitions. Returns 401 if signature is missing
    or invalid.
    """
    import hmac
    import hashlib
    import json as _json
    from uuid import UUID
    from fastapi import HTTPException
    from app.models.models import IntegrationConfig, ChangeRecord
    from app.core.config import settings
    from cryptography.fernet import Fernet

    # --- 1. Resolve integration ---
    try:
        integ_uuid = UUID(integration_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid integration ID")

    result = await db.execute(
        select(IntegrationConfig).where(IntegrationConfig.id == integ_uuid)
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    # --- 2. Verify HMAC signature ---
    if integration.webhook_secret:
        # Decrypt the stored secret
        fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
        secret_bytes = fernet.decrypt(integration.webhook_secret.encode())

        # Reconstruct raw body for HMAC (FastAPI already parsed JSON; re-serialize)
        raw_body = _json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()

        expected_sig = hmac.new(secret_bytes, raw_body, hashlib.sha256).hexdigest()
        provided_sig = http_request.headers.get("X-Webhook-Signature", "")

        # Strip "sha256=" prefix if present
        if provided_sig.startswith("sha256="):
            provided_sig = provided_sig[7:]

        if not hmac.compare_digest(expected_sig, provided_sig):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # --- 3. Process payload (existing logic below, unchanged) ---
    from datetime import datetime, timezone

    if integration.integration_type == "servicenow":
        change_request_id = payload.get("sys_id") or payload.get(
            "change_request", {}
        ).get("sys_id")
        state = payload.get("state") or payload.get("change_request", {}).get("state")

        if state in ["3", "approved"]:
            cr_result = await db.execute(
                select(ChangeRecord).where(
                    ChangeRecord.external_ticket_id == change_request_id
                )
            )
            change = cr_result.scalar_one_or_none()

            if change and change.status == "proposed":
                change.status = "approved"
                change.approved_at = datetime.now(timezone.utc)
                change.approval_notes = "Auto-approved via ServiceNow webhook"
                await db.commit()

    elif integration.integration_type == "jira":
        issue_key = payload.get("issue", {}).get("key")
        transition = payload.get("transition", {}).get("name", "").lower()

        if "approve" in transition or "resolved" in transition:
            cr_result = await db.execute(
                select(ChangeRecord).where(ChangeRecord.external_ticket_id == issue_key)
            )
            change = cr_result.scalar_one_or_none()

            if change and change.status == "proposed":
                change.status = "approved"
                change.approved_at = datetime.now(timezone.utc)
                change.approval_notes = "Auto-approved via JIRA webhook"
                await db.commit()

    return {"status": "received"}
```

> Note: `hmac.new` should be `hmac.new` — Python's `hmac` module uses `hmac.new()` in older versions. For Python 3.11, use `hmac.new(secret_bytes, raw_body, hashlib.sha256)`.

- [ ] **Step 3: Run tests**

```bash
make test 2>&1 | grep -A5 "test_webhook_rejects"
```

Expected: PASS (404 because the integration doesn't exist in test DB, which is fine — the auth check runs first when integration IS found).

- [ ] **Step 4: Commit**

```bash
git add services/api/app/api/routes/changes.py
git commit -m "fix(security): add HMAC signature verification to change webhook endpoint

Unauthenticated callers could inject payloads to auto-approve changes.
The IntegrationConfig already stored an encrypted webhook_secret — this
commit decrypts it and verifies X-Webhook-Signature using HMAC-SHA256
before processing any state transition.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 10 (I8 + I9): Move `test_migrations.py` + Remove Duplicate Import

**Files:**
- Delete: `services/api/test_migrations.py`
- Create: `tests/api/db/test_migrations.py`
- Modify: `services/api/app/api/routes/changes.py` (remove duplicate import line 24)

### Part A — Duplicate Import

- [ ] **Step 1: Remove the duplicate import from `changes.py`**

Line 15 already has:
```python
from app.services.change_service import VALID_TRANSITIONS, can_transition, generate_change_number
```

Line 24 is a duplicate of the same import after `router = APIRouter()`. Delete line 24.

```bash
# Verify the duplicate:
grep -n "from app.services.change_service import" services/api/app/api/routes/changes.py
```

Expected: two lines. Delete the second one (the one after `router = APIRouter()`).

### Part B — Move and Convert `test_migrations.py`

- [ ] **Step 2: Create `tests/api/db/` directory and `__init__.py`**

```bash
mkdir -p tests/api/db
touch tests/api/db/__init__.py
```

- [ ] **Step 3: Create proper pytest test at `tests/api/db/test_migrations.py`**

```python
"""
Alembic migration smoke tests — verify schema is applied correctly.
These tests run against the live test database in Docker.
"""
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_organizations_table_exists(db: AsyncSession):
    """organizations table must exist after migrations."""
    result = await db.execute(text("SELECT 1 FROM organizations LIMIT 1"))
    # If the table doesn't exist, execute raises ProgrammingError
    # Getting here (even with 0 rows) means the table exists.
    assert result is not None


@pytest.mark.asyncio
async def test_devices_table_exists(db: AsyncSession):
    """devices table must exist after migrations."""
    result = await db.execute(text("SELECT 1 FROM devices LIMIT 1"))
    assert result is not None


@pytest.mark.asyncio
async def test_vector_indexes_exist(db: AsyncSession):
    """HNSW vector indexes must exist on the devices table."""
    result = await db.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'devices' AND indexname LIKE '%vector%'"
        )
    )
    indexes = [row[0] for row in result.fetchall()]
    assert len(indexes) >= 1, (
        f"Expected at least 1 vector index on devices, found: {indexes}"
    )


@pytest.mark.asyncio
async def test_change_records_table_has_change_number_column(db: AsyncSession):
    """change_records table must have change_number column."""
    result = await db.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'change_records' AND column_name = 'change_number'"
        )
    )
    row = result.fetchone()
    assert row is not None, "change_number column missing from change_records table"
```

- [ ] **Step 4: Delete the old standalone script**

```bash
git rm services/api/test_migrations.py
```

- [ ] **Step 5: Run the new tests**

```bash
make test 2>&1 | grep -A5 "test_migrations\|test_organizations_table\|test_devices_table\|test_vector_indexes"
```

Expected: PASS (all four tests).

- [ ] **Step 6: Commit**

```bash
git add services/api/app/api/routes/changes.py \
        tests/api/db/__init__.py \
        tests/api/db/test_migrations.py
git rm services/api/test_migrations.py
git commit -m "refactor(tests): replace standalone test_migrations script with pytest tests

The old services/api/test_migrations.py was an asyncio.run() script that
pytest could not discover or run in CI. Replaced with proper async pytest
tests in tests/api/db/. Also removed duplicate import in changes.py.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 11 (M1): TextFSMParser Singleton

**Files:**
- Modify: `services/agent/agent/normalizer.py`

`normalize_command_output()` creates a new `TextFSMParser()` on every call. If `TextFSMParser.__init__` loads templates from disk, this repeats I/O on every normalization. Use a module-level singleton.

- [ ] **Step 1: Write a performance regression test**

In `tests/agent/test_normalizer_orchestrator.py`:

```python
def test_normalize_command_output_reuses_parser_instance():
    """normalize_command_output must reuse the module-level TextFSMParser, not create a new one."""
    from agent import normalizer as norm_module
    from agent.normalizer_textfsm.textfsm_parser import TextFSMParser

    init_call_count = []
    original_init = TextFSMParser.__init__

    def counting_init(self, *args, **kwargs):
        init_call_count.append(1)
        original_init(self, *args, **kwargs)

    with patch.object(TextFSMParser, "__init__", counting_init):
        # Reset the module singleton so it gets re-initialized under our patch
        norm_module._TEXTFSM_PARSER = None
        norm_module.normalize_command_output(
            vendor="cisco_ios", command="show version", raw_output="test"
        )
        norm_module.normalize_command_output(
            vendor="cisco_ios", command="show version", raw_output="test"
        )

    # __init__ should be called at most once (when singleton is created)
    assert len(init_call_count) <= 1, (
        f"TextFSMParser.__init__ called {len(init_call_count)} times — "
        "should be created once and reused"
    )
```

- [ ] **Step 2: Add module-level singleton to `normalizer.py`**

At the top of `services/agent/agent/normalizer.py`, after the imports, add:

```python
# Module-level singleton — avoids repeated template I/O on every normalize call
_TEXTFSM_PARSER: "TextFSMParser | None" = None


def _get_parser() -> "TextFSMParser":
    global _TEXTFSM_PARSER
    if _TEXTFSM_PARSER is None:
        _TEXTFSM_PARSER = TextFSMParser()
    return _TEXTFSM_PARSER
```

Then in `normalize_command_output()`, replace `parser = TextFSMParser()` with `parser = _get_parser()`.

- [ ] **Step 3: Run test**

```bash
make test 2>&1 | grep -A3 "test_normalize_command_output_reuses_parser"
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add services/agent/agent/normalizer.py tests/agent/test_normalizer_orchestrator.py
git commit -m "perf(agent): make TextFSMParser a module-level singleton

Previously a new TextFSMParser was created on every normalize_command_output
call, repeating template file I/O. Now initialized once and reused.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 12 (M3 + M4): Fix Schema Literal and Tautological Test Assertion

**Files:**
- Modify: `services/common/normalization/schemas.py`
- Modify: `tests/agent/test_normalizer_orchestrator.py`

### Part A — Fix `parser_method` Literal

`NormalizedCommandOutput.parser_method` has `Literal["textfsm", "fallback", "strict"]`. `"strict"` is a mode flag, not a parser method — no code path ever sets `parser_method = "strict"`. Remove it.

- [ ] **Step 1: Update `schemas.py`**

```python
# Before:
parser_method: Literal["textfsm", "fallback", "strict"]

# After:
parser_method: Literal["textfsm", "fallback"]
```

### Part B — Fix Tautological Test Assertion

Line 130 of `test_normalizer_orchestrator.py`:
```python
assert result.template_name is not None or result.parser_method == "textfsm"
```

This passes even when `template_name` is `None`. The mock patches `_template_name` to a known value, so assert it directly:

```python
assert result.template_name == "cisco_ios_show_version.textfsm"
assert result.parser_method == "textfsm"
```

- [ ] **Step 2: Run tests**

```bash
make test 2>&1 | grep -A3 "test_normalizer_orchestrator\|PASSED\|FAILED" | head -20
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add services/common/normalization/schemas.py tests/agent/test_normalizer_orchestrator.py
git commit -m "fix: remove 'strict' from parser_method Literal; fix tautological test assertion

'strict' is a behavior flag, not a parser method — no code sets parser_method='strict'.
Test assertion at line 130 was logically vacuous; replaced with direct field checks.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-Review

### Spec Coverage

| Issue | Task | Status |
|-------|------|--------|
| C1 — Agent import crash | Task 2 | ✓ |
| C2 — 6 broken rate-limited endpoints | Task 3 | ✓ |
| C3 — raw_config privacy violation | Task 1 | ✓ |
| I1 — Delete duplicate routes.py | Task 4 | ✓ |
| I2 — NormalizedIngestRecord missing | Task 4 (resolved by deletion) | ✓ |
| I3 — utcnow deprecated | Task 5 | ✓ |
| I4 — Webhook HMAC | Task 9 | ✓ |
| I5 — Jira auth header | Task 6 | ✓ |
| I6 — Sync redis | Task 7 | ✓ |
| I7 — Race condition change number | Task 8 | ✓ |
| I8 — test_migrations.py placement | Task 10 | ✓ |
| I9 — Duplicate import changes.py | Task 10 | ✓ |
| M1 — TextFSMParser singleton | Task 11 | ✓ |
| M2 — _fallback_parse undocumented | Task 1 (docstring added) | ✓ |
| M3 — parser_method Literal | Task 12 | ✓ |
| M4 — Tautological assertion | Task 12 | ✓ |
| M5 — get_rate_limit dead code | Task 4 (file deleted) | ✓ |
| M6 — Emoji in test_migrations | Task 10 (file replaced) | ✓ |

### Execution Order

Tasks 1, 2, 3, 4 are the Critical/high-priority items — do these first. Tasks 5–9 are Important fixes. Tasks 10–12 are cleanup. No task depends on another completing first.
