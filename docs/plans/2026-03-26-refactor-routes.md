# Refactor routes.py into Domain-Specific Routers Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the monolithic `routes.py` (3,624 lines, 48 routes) into a modular `routes/` package following FastAPI best practices, while keeping all tests green after every single task.

**Architecture:**
```
app/api/routes/
    __init__.py        ← aggregate router; assembled from all sub-routers
    health.py          ← GET /health
    portal.py          ← GET /portal/overview
    websocket.py       ← WS  /ws/discoveries/{id}
    discoveries.py     ← /discoveries
    sites.py           ← /sites
    devices.py         ← /devices (CRUD + ML classifier sub-routes)
    agents.py          ← /agents + /agent/vectors upload
    path_visualizer.py ← /path/trace
    alerts.py          ← /alerts/rules + /alerts/events
    integrations.py    ← /integrations
    acl_snapshots.py   ← /acl-snapshots
    simulations.py     ← /simulations
    changes.py         ← /changes + /webhooks
```

**Tech Stack:** Python, FastAPI

**Why six tasks instead of five:**
The original plan's incremental approach had a fatal flaw — creating `routes/__init__.py` while `routes.py` still exists causes Python to silently shadow the old module with the new (empty) package, dropping all 48 routes immediately. This plan uses a **bridge step** (Task 2) to rename `routes.py` into the new package directory first, eliminating the conflict before any splitting begins.

---

## Task 1: Extract Shared Helpers and Fix `test_device_audit.py`

**Files:**
- Modify: `services/api/app/api/dependencies.py`
- Modify: `services/api/app/api/routes.py`
- Create: `services/api/app/services/change_service.py`

**Why first:** These are pure moves with no structural changes. Getting them done before the package split avoids having to update imports in multiple new files later.

**Step 1: Run the existing test suite to establish a green baseline**

```bash
cd /home/openether/NetDiscoverIT && make test
```
Expected: all tests pass. This is the baseline we must maintain after every task.

**Step 2: Move `get_rate_limit` to `dependencies.py`**

In `services/api/app/api/dependencies.py`, add after the existing imports:

```python
from fastapi import Request

def get_rate_limit(request: Request) -> str:
    """Determine rate limit based on request method"""
    if request.method in ["POST", "PATCH", "DELETE", "PUT"]:
        return settings.RATE_LIMIT_WRITE
    return settings.RATE_LIMIT_READ
```

In `services/api/app/api/routes.py`:
- Remove the `get_rate_limit` function definition (lines 29–33)
- Add `get_rate_limit` to the existing import: `from app.api.dependencies import get_db, get_current_user, get_agent_auth, get_rate_limit`

**Step 3: Create `change_service.py`**

Create `services/api/app/services/change_service.py` and move into it from `routes.py`:
- The `VALID_TRANSITIONS` dict
- The `can_transition(current_status, new_status)` function
- The `generate_change_number(db)` async function

The service file needs these imports:
```python
from datetime import datetime
from typing import Dict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import ChangeRecord
```

In `routes.py`, replace the moved definitions with:
```python
from app.services.change_service import VALID_TRANSITIONS, can_transition, generate_change_number
```

**Step 4: Run tests**

```bash
make test
```
Expected: PASS — zero behavioural change, only file locations moved.

**Step 5: Commit**

```bash
git add services/api/app/api/dependencies.py \
        services/api/app/api/routes.py \
        services/api/app/services/change_service.py
git commit -m "refactor: extract rate limit helper and change service from routes"
```

---

## Task 2: Create the Routes Package (Bridge Step)

**Files:**
- Rename: `services/api/app/api/routes.py` → `services/api/app/api/routes/_legacy.py`
- Create:  `services/api/app/api/routes/__init__.py`

**Why this matters:** Python cannot have both `routes.py` and `routes/` importable simultaneously — the package always wins. This task resolves that by moving `routes.py` *into* the new package as `_legacy.py` before any splitting begins. `main.py` is not touched.

**Step 1: Create the package directory and move the file**

```bash
mkdir -p services/api/app/api/routes
mv services/api/app/api/routes.py services/api/app/api/routes/_legacy.py
```

**Step 2: Create `routes/__init__.py`**

```python
"""
API routes package.

During migration, _legacy.py holds all routes not yet split into their own module.
__init__.py re-exports `router` so main.py needs no changes.
`from ._legacy import *` keeps test_device_audit.py working until devices.py is created in Task 4.
"""
from ._legacy import router       # main.py: `from app.api import routes; routes.router` still works
from ._legacy import *            # exposes list_devices, dependencies, etc. for existing tests
```

**Step 3: Run tests**

```bash
make test
```
Expected: PASS — identical behaviour, `_legacy.py` is just `routes.py` in a new location.

**Step 4: Commit**

```bash
git add services/api/app/api/routes/
git commit -m "refactor: establish routes package with _legacy bridge"
```

---

## Task 3: Extract Health, Portal, WebSocket, Discoveries, and Sites

**Files:**
- Create: `services/api/app/api/routes/health.py`
- Create: `services/api/app/api/routes/portal.py`
- Create: `services/api/app/api/routes/websocket.py`
- Create: `services/api/app/api/routes/discoveries.py`
- Create: `services/api/app/api/routes/sites.py`
- Modify: `services/api/app/api/routes/_legacy.py`
- Modify: `services/api/app/api/routes/__init__.py`

**Step 1: Create each new router file**

Each file follows this pattern — copy the relevant routes out of `_legacy.py`, add the necessary imports, and define a local `router = APIRouter()`.

**`health.py`** — contains `GET /health` and `health_check()`.

**`portal.py`** — contains `GET /portal/overview` and `portal_overview()`.
Imports needed: `APIRouter`, `Depends`, `AsyncSession`, `select`, `schemas`, `dependencies`, `Device`, `AlertEvent`, `Discovery`, `get_db`.

**`websocket.py`** — contains `WS /ws/discoveries/{discovery_id}` and `websocket_discovery_status()`.
Imports needed: `APIRouter`, `WebSocket`, `WebSocketDisconnect`.

**`discoveries.py`** — contains `POST /discoveries` and `GET /discoveries/{discovery_id}`.
Imports needed: `APIRouter`, `HTTPException`, `Depends`, `AsyncSession`, `select`, `UUID`, `schemas`, `dependencies`, `Discovery`, `get_db`.

**`sites.py`** — contains the `_site_response()` helper and all five `/sites` routes.
Imports needed: `APIRouter`, `HTTPException`, `Depends`, `Request`, `AsyncSession`, `select`, `List`, `UUID`, `schemas`, `dependencies`, `Site`, `get_db`, `get_rate_limit`, `limiter` (from slowapi).

**Step 2: Remove moved routes from `_legacy.py`**

Delete the corresponding route functions and the `_site_response` helper from `_legacy.py`. Do not remove any imports yet — leave them for the final cleanup in Task 6.

**Step 3: Update `__init__.py` to aggregate**

```python
from fastapi import APIRouter
from . import health, portal, websocket, discoveries, sites
from ._legacy import router as _legacy_router
from ._legacy import *  # still needed: list_devices etc. still live in _legacy

router = APIRouter()
router.include_router(health.router)
router.include_router(portal.router)
router.include_router(websocket.router, tags=["websocket"])
router.include_router(discoveries.router, prefix="/discoveries", tags=["discoveries"])
router.include_router(sites.router, prefix="/sites", tags=["sites"])
router.include_router(_legacy_router)   # devices, agents, alerts, integrations, changes, etc.
```

**Step 4: Run tests**

```bash
make test
```
Expected: PASS.

**Step 5: Commit**

```bash
git add services/api/app/api/routes/
git commit -m "refactor: extract health, portal, websocket, discoveries, sites routes"
```

---

## Task 4: Extract Devices, Agents, and Path Visualizer — and Fix `test_device_audit.py`

**Files:**
- Create: `services/api/app/api/routes/devices.py`
- Create: `services/api/app/api/routes/agents.py`
- Create: `services/api/app/api/routes/path_visualizer.py`
- Modify: `services/api/app/api/routes/_legacy.py`
- Modify: `services/api/app/api/routes/__init__.py`
- Modify: `services/api/tests/api/test_device_audit.py`

**Step 1: Create `devices.py`**

Contains: `_device_response()` helper, all five device CRUD routes, and the three ML classifier routes (`classify`, `classification`, `classify-batch`).

**Critical — route registration order:** The static segment `/classify-batch` must be registered **before** the parametric `/{device_id}` routes. Without a UUID regex constraint on `{device_id}`, FastAPI would match `/devices/classify-batch` against `{device_id}` first and return a 422. Register the batch route first:

```python
router = APIRouter()

# Static routes first — must precede /{device_id} parametric routes
@router.post("/classify-batch")           # → POST /devices/classify-batch
async def batch_classify_devices(...): ...

# Parametric routes after
@router.get("/", ...)                      # → GET /devices
@router.post("/", ...)                     # → POST /devices
@router.get("/{device_id}", ...)           # → GET /devices/{device_id}
@router.patch("/{device_id}", ...)
@router.delete("/{device_id}", ...)
@router.post("/{device_id}/classify", ...) # → POST /devices/{device_id}/classify
@router.get("/{device_id}/classification", ...)
```

`get_classifier` dependency factory and `_device_response` helper also live in this file.

**Step 2: Create `agents.py`**

Contains: `POST /agent/vectors` and all five `/agents` routes.
Note: the agent upload route (`POST /agent/vectors`) has no `/agents` prefix — register it without one:

```python
@router.post("/agent/vectors")    # not /agents/vectors
```

When included in `__init__.py`, include it with no prefix: `router.include_router(agents.router, tags=["agents"])`.

**Step 3: Create `path_visualizer.py`**

Contains: `POST /path/trace` and `trace_path()`.

**Critical — do not change the URL.** Include in `__init__.py` with no prefix:
```python
router.include_router(path_visualizer.router, tags=["path"])
```
This preserves `POST /api/v1/path/trace`. The original plan used `prefix="/topology"` which would have changed the URL to `/topology/path/trace` — a breaking change.

**Step 4: Remove moved routes from `_legacy.py`**

Delete device CRUD, ML classifier, agents, and path visualizer routes from `_legacy.py`.

**Step 5: Fix `test_device_audit.py`**

This test directly imports and calls route functions from the old `routes` module. Now that device functions live in `devices.py`, the `from ._legacy import *` in `__init__.py` no longer exposes them. Update the test:

```python
# Old
from app.api import routes
...
routes.dependencies.audit_log = capture_audit_log
original_routes_audit_log = routes.dependencies.audit_log
await routes.list_devices(current_user=mock_user, db=mock_db)
await routes.get_device(...)
await routes.create_device(...)
await routes.update_device(...)
await routes.delete_device(...)
...
routes.dependencies.audit_log = original_routes_audit_log

# New
from app.api.routes import devices
...
original_devices_audit_log = devices.dependencies.audit_log
devices.dependencies.audit_log = capture_audit_log
await devices.list_devices(current_user=mock_user, db=mock_db)
await devices.get_device(...)
await devices.create_device(...)
await devices.update_device(...)
await devices.delete_device(...)
...
devices.dependencies.audit_log = original_devices_audit_log
```

This works because `devices.py` imports `dependencies` as a module (`from app.api import dependencies`), so patching `devices.dependencies.audit_log` patches the same underlying module attribute that the route functions call.

**Step 6: Update `__init__.py`**

```python
from fastapi import APIRouter
from . import health, portal, websocket, discoveries, sites
from . import devices, agents, path_visualizer
from ._legacy import router as _legacy_router
# from ._legacy import * no longer needed — test_device_audit now imports from devices directly

router = APIRouter()
router.include_router(health.router)
router.include_router(portal.router)
router.include_router(websocket.router, tags=["websocket"])
router.include_router(discoveries.router, prefix="/discoveries", tags=["discoveries"])
router.include_router(sites.router, prefix="/sites", tags=["sites"])
router.include_router(devices.router, prefix="/devices", tags=["devices"])
router.include_router(agents.router, tags=["agents"])
router.include_router(path_visualizer.router, tags=["path"])
router.include_router(_legacy_router)   # alerts, integrations, acl_snapshots, simulations, changes remain
```

**Step 7: Run tests**

```bash
make test
```
Expected: PASS.

**Step 8: Commit**

```bash
git add services/api/app/api/routes/ \
        services/api/tests/api/test_device_audit.py
git commit -m "refactor: extract devices, agents, path_visualizer routes; fix test_device_audit imports"
```

---

## Task 5: Extract Alerts, Integrations, ACL Snapshots, and Simulations

**Files:**
- Create: `services/api/app/api/routes/alerts.py`
- Create: `services/api/app/api/routes/integrations.py`
- Create: `services/api/app/api/routes/acl_snapshots.py`
- Create: `services/api/app/api/routes/simulations.py`
- Modify: `services/api/app/api/routes/_legacy.py`
- Modify: `services/api/app/api/routes/__init__.py`

**Step 1: Create each new router file**

**`alerts.py`** — 8 routes under `/alerts/rules` and `/alerts/events`.
Register routes without a prefix (they already start with `/alerts/...`).
Include in `__init__.py` with no prefix: `router.include_router(alerts.router, tags=["alerts"])`.

**`integrations.py`** — 6 routes.
Include with `prefix="/integrations"`.

**`acl_snapshots.py`** — 5 routes.
Include with `prefix="/acl-snapshots"`.

**`simulations.py`** — 2 routes.
Include with `prefix="/simulations"`.

**Step 2: Remove moved routes from `_legacy.py`**

After this task, `_legacy.py` should contain only the changes routes and the webhook route (~960 lines).

**Step 3: Update `__init__.py`**

```python
from fastapi import APIRouter
from . import health, portal, websocket, discoveries, sites
from . import devices, agents, path_visualizer
from . import alerts, integrations, acl_snapshots, simulations
from ._legacy import router as _legacy_router  # changes + webhook only

router = APIRouter()
router.include_router(health.router)
router.include_router(portal.router)
router.include_router(websocket.router, tags=["websocket"])
router.include_router(discoveries.router, prefix="/discoveries", tags=["discoveries"])
router.include_router(sites.router, prefix="/sites", tags=["sites"])
router.include_router(devices.router, prefix="/devices", tags=["devices"])
router.include_router(agents.router, tags=["agents"])
router.include_router(path_visualizer.router, tags=["path"])
router.include_router(alerts.router, tags=["alerts"])
router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])
router.include_router(acl_snapshots.router, prefix="/acl-snapshots", tags=["acl-snapshots"])
router.include_router(simulations.router, prefix="/simulations", tags=["simulations"])
router.include_router(_legacy_router)
```

**Step 4: Run tests**

```bash
make test
```
Expected: PASS.

**Step 5: Commit**

```bash
git add services/api/app/api/routes/
git commit -m "refactor: extract alerts, integrations, acl_snapshots, simulations routes"
```

---

## Task 6: Extract Changes, Delete `_legacy.py`, and Finalise

**Files:**
- Create: `services/api/app/api/routes/changes.py`
- Delete: `services/api/app/api/routes/_legacy.py`
- Modify: `services/api/app/api/routes/__init__.py`

**Step 1: Create `changes.py`**

This is the largest single file (~960 lines). Contains:
- `generate_change_number` import from `change_service`
- `can_transition` import from `change_service`
- `VALID_TRANSITIONS` import from `change_service`
- All 12 `/changes` routes (full lifecycle: create, list, get, patch, delete, approve, schedule, implement, verify, rollback, attach-evidence)
- `POST /webhooks/change/{integration_id}`

Imports needed:
```python
from app.services.change_service import VALID_TRANSITIONS, can_transition, generate_change_number
```

**Step 2: Verify `_legacy.py` is now empty of routes**

At this point `_legacy.py` should contain only its original imports and the `router = APIRouter()` declaration with no routes registered on it. Double-check before deleting.

**Step 3: Delete `_legacy.py` and update `__init__.py`**

```bash
git rm services/api/app/api/routes/_legacy.py
```

Final `__init__.py` — clean, no `_legacy` references:

```python
"""
API routes package — aggregates all domain-specific routers.
"""
from fastapi import APIRouter
from . import health, portal, websocket
from . import discoveries, sites
from . import devices, agents, path_visualizer
from . import alerts, integrations
from . import acl_snapshots, simulations
from . import changes

router = APIRouter()

router.include_router(health.router)
router.include_router(portal.router)
router.include_router(websocket.router,       tags=["websocket"])
router.include_router(discoveries.router,     prefix="/discoveries",   tags=["discoveries"])
router.include_router(sites.router,           prefix="/sites",         tags=["sites"])
router.include_router(devices.router,         prefix="/devices",       tags=["devices"])
router.include_router(agents.router,                                   tags=["agents"])
router.include_router(path_visualizer.router,                          tags=["path"])
router.include_router(alerts.router,                                   tags=["alerts"])
router.include_router(integrations.router,    prefix="/integrations",  tags=["integrations"])
router.include_router(acl_snapshots.router,   prefix="/acl-snapshots", tags=["acl-snapshots"])
router.include_router(simulations.router,     prefix="/simulations",   tags=["simulations"])
router.include_router(changes.router,                                  tags=["changes"])
```

**`main.py` requires no changes** — it does `from app.api import routes; routes.router` which resolves to `routes/__init__.py`'s `router` both before and after this refactor.

**Step 4: Run full test suite**

```bash
make test
```
Expected: PASS — full green baseline restored with modular structure.

**Step 5: Commit**

```bash
git add services/api/app/api/routes/
git commit -m "refactor: extract changes routes and remove _legacy bridge, routes split complete"
```

---

## Summary

| Task | Description | Risk | Tests |
|------|-------------|------|-------|
| 1 | Extract helpers + change_service | Low | ✅ Pass |
| 2 | Create package, move to `_legacy.py` (bridge) | Low | ✅ Pass |
| 3 | Extract health, portal, ws, discoveries, sites | Low | ✅ Pass |
| 4 | Extract devices, agents, path_visualizer; fix test | Medium | ✅ Pass |
| 5 | Extract alerts, integrations, acl, simulations | Low | ✅ Pass |
| 6 | Extract changes, delete `_legacy.py`, finalise | Low | ✅ Pass |

**Final state:** 13 focused router files averaging ~280 lines each, down from one 3,624-line file. `main.py` unchanged.

---

## Key Decisions (corrections from original plan)

1. **Bridge step (Task 2)** — renames `routes.py` into the new package as `_legacy.py` before any splitting. Eliminates the Python package-vs-module shadowing conflict that would have dropped all routes at Task 1 of the original plan.

2. **`from ._legacy import *` in `__init__.py` during Tasks 2–3** — keeps `test_device_audit.py` working without touching it until its natural point of failure (Task 4, when `list_devices` moves out of `_legacy`). Removed once `test_device_audit.py` is updated.

3. **`/path/trace` URL preserved** — `path_visualizer.router` is included with no prefix. The original plan used `prefix="/topology"` which would have changed the live URL.

4. **`classify-batch` registered before `/{device_id}` in `devices.py`** — prevents FastAPI from greedily matching the string `classify-batch` as a UUID `device_id`.

5. **`test_device_audit.py` updated in Task 4** — changes `from app.api import routes` → `from app.api.routes import devices` and updates all direct function calls and monkey-patching accordingly.
