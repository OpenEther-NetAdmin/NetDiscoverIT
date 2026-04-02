# Test Directory Consolidation — Design Spec

**Date:** 2026-04-02
**Status:** Approved

## Problem

Tests are scattered across three directories:
- `tests/` (root) — the only location run by `make test` (`pytest tests/ -v`)
- `services/api/tests/` — ~30 test files, never run
- `services/agent/tests/` — 1 orphan file, never run

Additionally a stale git worktree exists at `.worktrees/group5-textfsm/` for an abandoned
in-progress Group 5 branch.

## Goal

Consolidate all tests under `tests/` so `make test` runs the full suite. Keep `make test`
command unchanged. Add a `pytest.ini` to set `pythonpath` correctly for both service import
namespaces.

## Target Structure

```
tests/
├── conftest.py                              # from services/api/tests/conftest.py
├── agent/
│   ├── fixtures/                            # keep as-is from tests/agent/fixtures/
│   ├── sanitizer/
│   │   └── tiers/
│   │       └── test_tier3_regex.py          # whitespace-only diff; use svc version
│   ├── test_full_vectorizer_pipeline.py     # from services/agent/tests/
│   ├── test_normalizer.py
│   ├── test_normalizer_orchestrator.py      # svc-only (new)
│   ├── test_normalizer_schemas.py           # svc-only (new)
│   ├── test_redaction_logger.py
│   ├── test_sanitizer.py
│   ├── test_sanitizer_units.py
│   ├── test_sanitizer_with_fixtures.py
│   ├── test_textfsm_parser.py               # svc-only (new)
│   ├── test_token_mapper.py
│   ├── test_uploader.py                     # svc version, import fixed to agent.uploader
│   └── test_vectorizer.py                   # identical; use svc version
├── api/
│   ├── auth/                                # svc-only (new subtree)
│   │   ├── test_agent_auth.py
│   │   ├── test_refresh_token.py
│   │   └── test_registration.py
│   ├── db/
│   │   └── test_migrations.py               # 27-line version (root == svc/api/db)
│   ├── routes/
│   │   └── test_agents.py                   # svc version (157 lines vs root 18)
│   ├── test_alerting_api.py
│   ├── test_alerting_migrations.py
│   ├── test_audit_integration.py
│   ├── test_audit_log.py
│   ├── test_auth.py                         # svc version (trivial comma diff)
│   ├── test_compliance_reports.py           # svc-only (new)
│   ├── test_compliance_reports_integration.py
│   ├── test_device_audit.py
│   ├── test_device_metadata.py
│   ├── test_nli_integration.py
│   ├── test_nli_unit.py
│   ├── test_role_classification.py
│   ├── test_storage_integration.py
│   ├── test_storage_unit.py
│   └── test_topology.py                     # root-only (no svc counterpart)
├── core/
│   └── test_security.py
├── db/
│   └── test_migrations.py                   # 15-line svc/db version (different scope)
├── integration/
│   └── test_role_classifier_flow.py
├── services/
│   ├── test_alert_routing.py
│   ├── test_role_classifier.py
│   └── test_role_classifier_service.py
├── tasks/
│   ├── __init__.py
│   ├── test_alert_routing.py
│   └── test_config_drift_alerts.py
└── test_upload_with_vectors.py
```

## Conflict Resolution Rules

| File | Decision | Reason |
|------|----------|--------|
| `test_auth.py` | Use svc version | Only trailing-comma diff; svc is more recent |
| `test_tier3_regex.py` | Use svc version | Whitespace-only diff; svc is more recent |
| `test_vectorizer.py` | Use svc version | Files are identical |
| `test_agents.py` | Use svc version | 157 lines vs 18 lines; svc is comprehensive |
| `test_uploader.py` | Use svc version, fix import | Svc has better mock pattern; import `from agent.uploader` (not `agent.agent.uploader`) |
| `tests/api/db/test_migrations.py` | Use root/svc-api-db version (27 lines) | Both identical at 27 lines |
| `tests/db/test_migrations.py` | Keep svc/db version (15 lines) | Different scope; tests different migrations |
| `test_topology.py` | Keep root version | No svc counterpart exists |

## pytest.ini (new file at repo root)

```ini
[pytest]
pythonpath = services/api services/agent
testpaths = tests
asyncio_mode = auto
```

`pythonpath` entries allow:
- `from app.xxx` imports (API tests) → resolved via `services/api/`
- `from agent.xxx` imports (agent tests) → resolved via `services/agent/`

## Makefile

No changes needed. `make test` stays as `pytest tests/ -v`. The new `pytest.ini` at root
handles pythonpath automatically.

## Worktree Cleanup

- **Remove** `.worktrees/group5-textfsm/` working directory:
  `git worktree remove .worktrees/group5-textfsm --force`
- **Keep** the `feature/group5-textfsm` branch — it has a partial TextFSM implementation
  (one commit: `b9fb5cd`) that may be useful when Group 5 work resumes.
- Remove `.worktrees/` directory once empty.

## Deletions After Consolidation

Once tests are merged into `tests/`:
- `services/api/tests/` — remove entirely
- `services/agent/tests/` — remove entirely
- `tests/agent/sanitizer/` duplicate in root (only the consolidated version remains)

## What Is NOT Changed

- `make test` command
- `services/api/app/` source code
- `services/agent/agent/` source code
- Any frontend tests
- The `feature/group5-textfsm` branch (kept for future use)
