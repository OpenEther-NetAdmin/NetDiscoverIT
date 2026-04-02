# Test Directory Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate all test files under `tests/` so `make test` runs the full suite without changing the Makefile.

**Architecture:** Add `pytest.ini` at the repo root to set `pythonpath = services/api services/agent`, copy `services/api/tests/conftest.py` → `tests/conftest.py`, move all unique and conflict-resolved test files into the correct location under `tests/`, verify, then delete the old directories and remove the stale worktree.

**Tech Stack:** pytest, pytest-asyncio, existing FastAPI test fixtures

---

## File Map

| Action | Source | Destination |
|--------|--------|-------------|
| Create | _(new)_ | `pytest.ini` |
| Move | `services/api/tests/conftest.py` | `tests/conftest.py` |
| Move (new) | `services/api/tests/__init__.py` | _(discard — not needed in tests/)_ |
| Move (new) | `services/api/tests/api/auth/test_agent_auth.py` | `tests/api/auth/test_agent_auth.py` |
| Move (new) | `services/api/tests/api/auth/test_refresh_token.py` | `tests/api/auth/test_refresh_token.py` |
| Move (new) | `services/api/tests/api/auth/test_registration.py` | `tests/api/auth/test_registration.py` |
| Move (new) | `services/api/tests/api/test_alerting_api.py` | `tests/api/test_alerting_api.py` |
| Move (new) | `services/api/tests/api/test_alerting_migrations.py` | `tests/api/test_alerting_migrations.py` |
| Move (new) | `services/api/tests/api/test_audit_integration.py` | `tests/api/test_audit_integration.py` |
| Move (new) | `services/api/tests/api/test_audit_log.py` | `tests/api/test_audit_log.py` |
| Move (new) | `services/api/tests/api/test_compliance_reports.py` | `tests/api/test_compliance_reports.py` |
| Move (new) | `services/api/tests/api/test_compliance_reports_integration.py` | `tests/api/test_compliance_reports_integration.py` |
| Move (new) | `services/api/tests/api/test_device_audit.py` | `tests/api/test_device_audit.py` |
| Move (new) | `services/api/tests/api/test_device_metadata.py` | `tests/api/test_device_metadata.py` |
| Move (new) | `services/api/tests/api/test_nli_integration.py` | `tests/api/test_nli_integration.py` |
| Move (new) | `services/api/tests/api/test_nli_unit.py` | `tests/api/test_nli_unit.py` |
| Move (new) | `services/api/tests/api/test_role_classification.py` | `tests/api/test_role_classification.py` |
| Move (new) | `services/api/tests/api/test_storage_integration.py` | `tests/api/test_storage_integration.py` |
| Move (new) | `services/api/tests/api/test_storage_unit.py` | `tests/api/test_storage_unit.py` |
| Move (new) | `services/api/tests/core/test_security.py` | `tests/core/test_security.py` |
| Move (new) | `services/api/tests/db/test_migrations.py` | `tests/db/test_migrations.py` |
| Move (new) | `services/api/tests/integration/test_role_classifier_flow.py` | `tests/integration/test_role_classifier_flow.py` |
| Move (new) | `services/api/tests/services/test_alert_routing.py` | `tests/services/test_alert_routing.py` |
| Move (new) | `services/api/tests/services/test_role_classifier.py` | `tests/services/test_role_classifier.py` |
| Move (new) | `services/api/tests/services/test_role_classifier_service.py` | `tests/services/test_role_classifier_service.py` |
| Move (new) | `services/api/tests/tasks/__init__.py` | `tests/tasks/__init__.py` _(already exists — skip)_ |
| Move (new) | `services/api/tests/tasks/test_alert_routing.py` | `tests/tasks/test_alert_routing.py` |
| Move (new) | `services/api/tests/tasks/test_config_drift_alerts.py` | `tests/tasks/test_config_drift_alerts.py` |
| Move (new) | `services/api/tests/test_upload_with_vectors.py` | `tests/test_upload_with_vectors.py` |
| Replace | `services/api/tests/api/routes/test_agents.py` | `tests/api/routes/test_agents.py` (157-line svc replaces 18-line root) |
| Replace | `services/api/tests/api/test_auth.py` | `tests/api/test_auth.py` (svc, trivial diff) |
| Replace | `services/api/tests/api/db/test_migrations.py` | `tests/api/db/test_migrations.py` (27-line, identical to root) |
| Replace+fix | `services/api/tests/agent/test_uploader.py` | `tests/agent/test_uploader.py` (svc + fix import line 8) |
| Replace | `services/api/tests/agent/test_vectorizer.py` | `tests/agent/test_vectorizer.py` (identical) |
| Replace | `services/api/tests/agent/sanitizer/tiers/test_tier3_regex.py` | `tests/agent/sanitizer/tiers/test_tier3_regex.py` (whitespace only diff) |
| Move (new) | `services/agent/tests/test_full_vectorizer_pipeline.py` | `tests/agent/test_full_vectorizer_pipeline.py` |
| Delete | `services/api/tests/` | _(entire tree)_ |
| Delete | `services/agent/tests/` | _(entire tree)_ |
| Remove | `.worktrees/group5-textfsm/` | _(git worktree remove)_ |

---

### Task 1: Create pytest.ini

**Files:**
- Create: `pytest.ini`

- [ ] **Step 1: Create `pytest.ini` at repo root**

```ini
[pytest]
pythonpath = services/api services/agent
testpaths = tests
asyncio_mode = auto
```

- [ ] **Step 2: Verify pytest picks it up**

```bash
cd /home/openether/NetDiscoverIT
python -m pytest --co -q 2>&1 | head -20
```

Expected: pytest lists test files under `tests/` without import errors. Some tests may fail (DB not running) but collection should succeed.

---

### Task 2: Add conftest.py to tests/

**Files:**
- Create: `tests/conftest.py` (copied from `services/api/tests/conftest.py`)

- [ ] **Step 1: Copy conftest.py**

```bash
cp services/api/tests/conftest.py tests/conftest.py
```

- [ ] **Step 2: Verify the file landed correctly**

```bash
head -10 tests/conftest.py
```

Expected: First line is `"""` then `Test configuration and fixtures`.

---

### Task 3: Copy new unique files from services/api/tests/

These files exist only in `services/api/tests/` and have no counterpart in `tests/`. Create the destination directories and copy them all.

**Files:**
- Create dirs: `tests/api/auth/`, `tests/core/`, `tests/db/`, `tests/integration/`, `tests/services/`
- Copy 27 files (listed in the file map above under "Move (new)")

- [ ] **Step 1: Create missing subdirectories**

```bash
mkdir -p tests/api/auth
mkdir -p tests/core
mkdir -p tests/db
mkdir -p tests/integration
mkdir -p tests/services
```

- [ ] **Step 2: Copy api/auth tests**

```bash
cp services/api/tests/api/auth/test_agent_auth.py  tests/api/auth/test_agent_auth.py
cp services/api/tests/api/auth/test_refresh_token.py tests/api/auth/test_refresh_token.py
cp services/api/tests/api/auth/test_registration.py tests/api/auth/test_registration.py
```

- [ ] **Step 3: Copy api-level tests**

```bash
cp services/api/tests/api/test_alerting_api.py              tests/api/test_alerting_api.py
cp services/api/tests/api/test_alerting_migrations.py       tests/api/test_alerting_migrations.py
cp services/api/tests/api/test_audit_integration.py         tests/api/test_audit_integration.py
cp services/api/tests/api/test_audit_log.py                 tests/api/test_audit_log.py
cp services/api/tests/api/test_compliance_reports.py        tests/api/test_compliance_reports.py
cp services/api/tests/api/test_compliance_reports_integration.py tests/api/test_compliance_reports_integration.py
cp services/api/tests/api/test_device_audit.py              tests/api/test_device_audit.py
cp services/api/tests/api/test_device_metadata.py           tests/api/test_device_metadata.py
cp services/api/tests/api/test_nli_integration.py           tests/api/test_nli_integration.py
cp services/api/tests/api/test_nli_unit.py                  tests/api/test_nli_unit.py
cp services/api/tests/api/test_role_classification.py       tests/api/test_role_classification.py
cp services/api/tests/api/test_storage_integration.py       tests/api/test_storage_integration.py
cp services/api/tests/api/test_storage_unit.py              tests/api/test_storage_unit.py
```

- [ ] **Step 4: Copy non-api service-level tests**

```bash
cp services/api/tests/core/test_security.py                         tests/core/test_security.py
cp services/api/tests/db/test_migrations.py                         tests/db/test_migrations.py
cp services/api/tests/integration/test_role_classifier_flow.py      tests/integration/test_role_classifier_flow.py
cp services/api/tests/services/test_alert_routing.py                tests/services/test_alert_routing.py
cp services/api/tests/services/test_role_classifier.py              tests/services/test_role_classifier.py
cp services/api/tests/services/test_role_classifier_service.py      tests/services/test_role_classifier_service.py
cp services/api/tests/tasks/test_alert_routing.py                   tests/tasks/test_alert_routing.py
cp services/api/tests/tasks/test_config_drift_alerts.py             tests/tasks/test_config_drift_alerts.py
cp services/api/tests/test_upload_with_vectors.py                   tests/test_upload_with_vectors.py
```

- [ ] **Step 5: Verify file counts**

```bash
find tests/ -name "*.py" | wc -l
```

Expected: noticeably more than before (was ~11 files, now should be ~40+).

---

### Task 4: Resolve conflicts — replace root files with svc versions

Seven files exist in both locations. Per the spec's resolution table, the svc versions win (more comprehensive or more recent). One file needs an import path fix.

**Files:**
- Modify: `tests/api/routes/test_agents.py` (replace 18-line with 157-line svc version)
- Modify: `tests/api/test_auth.py` (replace with svc version)
- Modify: `tests/api/db/test_migrations.py` (replace with svc version — identical content)
- Modify: `tests/agent/test_vectorizer.py` (replace with svc version — identical content)
- Modify: `tests/agent/sanitizer/tiers/test_tier3_regex.py` (replace with svc version — whitespace only)
- Modify: `tests/agent/test_uploader.py` (replace with svc version + fix import)

- [ ] **Step 1: Replace straightforward conflicts (no import changes needed)**

```bash
cp services/api/tests/api/routes/test_agents.py          tests/api/routes/test_agents.py
cp services/api/tests/api/test_auth.py                   tests/api/test_auth.py
cp services/api/tests/api/db/test_migrations.py          tests/api/db/test_migrations.py
cp services/api/tests/agent/test_vectorizer.py           tests/agent/test_vectorizer.py
cp services/api/tests/agent/sanitizer/tiers/test_tier3_regex.py \
   tests/agent/sanitizer/tiers/test_tier3_regex.py
```

- [ ] **Step 2: Copy svc uploader test then fix the import**

```bash
cp services/api/tests/agent/test_uploader.py tests/agent/test_uploader.py
```

- [ ] **Step 3: Fix the wrong import in tests/agent/test_uploader.py**

The svc version uses `from agent.agent.uploader import VectorUploader` (line 8). With `pythonpath = services/agent`, the correct import is `from agent.uploader import VectorUploader`.

Open `tests/agent/test_uploader.py` and change line 8 from:
```python
from agent.agent.uploader import VectorUploader
```
to:
```python
from agent.uploader import VectorUploader
```

- [ ] **Step 4: Verify the import fix**

```bash
grep "from agent" tests/agent/test_uploader.py
```

Expected output:
```
from agent.uploader import VectorUploader
```

---

### Task 5: Move services/agent/tests orphan

**Files:**
- Move: `services/agent/tests/test_full_vectorizer_pipeline.py` → `tests/agent/test_full_vectorizer_pipeline.py`

- [ ] **Step 1: Copy the file**

```bash
cp services/agent/tests/test_full_vectorizer_pipeline.py \
   tests/agent/test_full_vectorizer_pipeline.py
```

- [ ] **Step 2: Verify it landed**

```bash
ls tests/agent/test_full_vectorizer_pipeline.py
```

Expected: file exists.

---

### Task 6: Verify make test collects everything correctly

Run test collection before deleting the old directories, so any issues can be diagnosed with the source still present.

- [ ] **Step 1: Dry-run collection**

```bash
cd /home/openether/NetDiscoverIT
python -m pytest tests/ --co -q 2>&1 | tail -20
```

Expected: A list of collected test IDs. No `ModuleNotFoundError` or `ImportError` in collection output. Some tests will show collection warnings if they require a live DB — that's acceptable. The count should be 100+ tests collected.

- [ ] **Step 2: Run tests that don't need Docker (unit tests only)**

```bash
python -m pytest tests/ -v \
  --ignore=tests/api/test_audit_integration.py \
  --ignore=tests/api/test_compliance_reports_integration.py \
  --ignore=tests/api/test_storage_integration.py \
  --ignore=tests/integration/ \
  --ignore=tests/db/ \
  -x -q 2>&1 | tail -30
```

Expected: Unit tests pass or fail for known reasons (missing env vars, no Ollama, etc.). The critical check is **no ImportError or ModuleNotFoundError** — those would indicate a missing `pythonpath` or wrong import in a file.

---

### Task 7: Delete old test directories

Only do this after Task 6 confirms no import errors.

**Files:**
- Delete: `services/api/tests/` (entire tree)
- Delete: `services/agent/tests/` (entire tree)

- [ ] **Step 1: Delete services/api/tests/**

```bash
rm -rf services/api/tests/
```

- [ ] **Step 2: Delete services/agent/tests/**

```bash
rm -rf services/agent/tests/
```

- [ ] **Step 3: Confirm they're gone**

```bash
ls services/api/tests 2>&1
ls services/agent/tests 2>&1
```

Expected: `No such file or directory` for both.

- [ ] **Step 4: Re-run collection to confirm nothing broke**

```bash
python -m pytest tests/ --co -q 2>&1 | tail -5
```

Expected: Same collection count as Task 6 Step 1. No new errors.

---

### Task 8: Remove the stale git worktree

The `feature/group5-textfsm` branch has one unmerged commit with a partial TextFSM implementation. We remove the working directory but keep the branch for future Group 5 work.

- [ ] **Step 1: Remove the worktree working directory**

```bash
git worktree remove .worktrees/group5-textfsm --force
```

Expected output: no error, or `Removing worktrees/group5-textfsm`.

- [ ] **Step 2: Confirm the branch still exists**

```bash
git branch | grep group5
```

Expected: `  feature/group5-textfsm` (branch present, just no working directory).

- [ ] **Step 3: Remove the now-empty .worktrees/ directory if empty**

```bash
rmdir .worktrees 2>/dev/null && echo "removed" || echo "not empty — leave it"
```

- [ ] **Step 4: Verify worktree list is clean**

```bash
git worktree list
```

Expected: Only one entry — the main working tree.

---

### Task 9: Commit

- [ ] **Step 1: Stage all changes**

```bash
git add pytest.ini
git add tests/
git add -u services/api/tests/ services/agent/tests/
```

- [ ] **Step 2: Verify staging looks correct**

```bash
git status --short | head -40
```

Expected: `A  pytest.ini`, many `A  tests/...` additions, many `D  services/api/tests/...` and `D  services/agent/tests/...` deletions. No unexpected modifications to source files.

- [ ] **Step 3: Commit**

```bash
git commit -m "$(cat <<'EOF'
refactor(tests): consolidate all tests under tests/ with pytest.ini pythonpath

- Move services/api/tests/ (30 files) and services/agent/tests/ (1 file) into tests/
- Add pytest.ini with pythonpath = services/api services/agent so both
  `from app.*` and `from agent.*` imports resolve correctly
- Copy tests/conftest.py from services/api/tests/conftest.py (richer fixtures)
- Resolve 7 filename conflicts: use svc versions throughout; fix
  agent/test_uploader.py import from agent.agent.uploader → agent.uploader
- Remove stale .worktrees/group5-textfsm working directory (branch kept)
- make test unchanged: pytest tests/ -v now runs full suite (~40+ files)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Verify commit landed**

```bash
git log --oneline -3
git show --stat HEAD | tail -15
```

Expected: New commit at top with the refactor message. Stat shows additions under `tests/` and deletions under `services/`.
