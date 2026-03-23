# Group 5 TextFSM Normalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the end-to-end TextFSM normalization pipeline, shared schema, and test coverage needed to support vendor-aware ML ingestion for both the local agent and cloud API.

**Architecture:** Build the normalization contract once and reuse it everywhere. The agent will normalize command output at collection time, while the API will validate the same payload shape during ingest so both paths stay aligned and testable. The plan uses a shared schema module and service-local wrappers so contract versioning stays explicit.

**Tech Stack:** Python 3.11, TextFSM, ntc-templates, Pydantic, pytest, Docker Compose, FastAPI

---

### Task 1: Define the normalized schema contract

**Files:**
- Create: `services/common/normalization/schemas.py`
- Modify: `services/agent/agent/normalizer/__init__.py`
- Modify: `services/api/app/api/schemas.py`
- Test: `services/agent/tests/test_normalizer_schemas.py`
- Test: `services/api/tests/api/test_normalized_ingest.py`

**Step 1: Write the failing test**

```python
from services.common.normalization.schemas import NormalizedCommandOutput


def test_normalized_command_output_requires_vendor_and_command():
    model = NormalizedCommandOutput(
        vendor="cisco_ios",
        command="show version",
        records=[{"hostname": "r1"}],
        parser_method="textfsm",
    )
    assert model.vendor == "cisco_ios"
```

**Step 2: Run test to verify it fails**

Run: `pytest services/agent/tests/test_normalizer_schemas.py -v`
Expected: FAIL because `NormalizedCommandOutput` does not exist.

**Step 3: Write minimal implementation**

Create a Pydantic model with vendor, command, records, parser_method, template_name, warnings, schema_version, template_source, parser_status, parser_confidence, fallback_reason, and normalized_at fields.

**Step 4: Run test to verify it passes**

Run: `pytest services/agent/tests/test_normalizer_schemas.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add services/common/normalization/schemas.py services/agent/tests/test_normalizer_schemas.py services/api/tests/api/test_normalized_ingest.py
git commit -m "feat(normalization): add shared normalized schema"
```

### Task 2: Add TextFSM template resolution and parsing coverage

**Files:**
- Create: `services/agent/agent/normalizer/textfsm_parser.py`
- Modify: `services/agent/agent/normalizer/__init__.py`
- Create: `services/common/normalization/__init__.py`
- Test: `services/agent/tests/test_textfsm_parser.py`

**Step 1: Write the failing test**

```python
from agent.normalizer.textfsm_parser import TextFSMParser


def test_resolve_template_returns_known_vendor_template():
    parser = TextFSMParser()
    template = parser.resolve_template("cisco_ios", "show version")
    assert template is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest services/agent/tests/test_textfsm_parser.py -v`
Expected: FAIL because parser module is missing.

**Step 3: Write minimal implementation**

Implement template lookup, cache handling, parse entry points, and a permissive fallback parser with explicit reason codes when a template is missing.

**Step 4: Run test to verify it passes**

Run: `pytest services/agent/tests/test_textfsm_parser.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add services/agent/agent/normalizer/textfsm_parser.py services/agent/tests/test_textfsm_parser.py services/common/normalization/__init__.py
git commit -m "feat(agent): add TextFSM template resolution"
```

### Task 3: Implement the normalization orchestrator

**Files:**
- Modify: `services/agent/agent/normalizer.py`
- Modify: `services/agent/agent/normalizer/__init__.py`
- Test: `services/agent/tests/test_normalizer_orchestrator.py`

**Step 1: Write the failing test**

```python
from agent.normalizer import normalize_command_output


def test_normalize_command_output_returns_canonical_payload():
    result = normalize_command_output("cisco_ios", "show version", "raw output")
    assert result.parser_method in {"textfsm", "fallback"}
```

**Step 2: Run test to verify it fails**

Run: `pytest services/agent/tests/test_normalizer_orchestrator.py -v`
Expected: FAIL because the orchestrator entry point is not implemented.

**Step 3: Write minimal implementation**

Route through the parser, populate the normalized schema, and preserve fallback metadata when template parsing is unavailable. Enforce strict/permissive mode behavior and sanitize before any cloud upload boundary.

**Step 4: Run test to verify it passes**

Run: `pytest services/agent/tests/test_normalizer_orchestrator.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add services/agent/agent/normalizer.py services/agent/tests/test_normalizer_orchestrator.py
git commit -m "feat(agent): wire TextFSM normalization orchestrator"
```

### Task 4: Add cloud-side schema validation for normalized uploads

**Files:**
- Modify: `services/api/app/api/schemas.py`
- Modify: `services/api/app/api/routes.py`
- Test: `services/api/tests/api/test_normalized_ingest.py`

**Step 1: Write the failing test**

```python
def test_normalized_upload_rejects_schema_mismatch(client):
    response = client.post("/api/v1/ingest/normalized", json={"bad": "payload"})
    assert response.status_code == 422
```

**Step 2: Run test to verify it fails**

Run: `pytest services/api/tests/api/test_normalized_ingest.py -v`
Expected: FAIL because the ingest route and schema are missing.

**Step 3: Write minimal implementation**

Add the normalized ingest schema and endpoint validation using the shared payload contract. Reject unsanitized payloads and validate the schema contract version before persistence.

**Step 4: Run test to verify it passes**

Run: `pytest services/api/tests/api/test_normalized_ingest.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add services/api/app/api/schemas.py services/api/app/api/routes.py services/api/tests/api/test_normalized_ingest.py
git commit -m "feat(api): validate normalized ingest payloads"
```

### Task 5: Add representative vendor coverage fixtures

**Files:**
- Create: `services/agent/tests/fixtures/textfsm/cisco_ios_show_version.txt`
- Create: `services/agent/tests/fixtures/textfsm/juniper_junos_show_version.txt`
- Create: `services/agent/tests/fixtures/textfsm/arista_eos_show_version.txt`
- Modify: `services/agent/tests/test_textfsm_parser.py`

**Step 1: Write the failing test**

```python
def test_supported_vendor_fixtures_parse_to_records():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest services/agent/tests/test_textfsm_parser.py -v`
Expected: FAIL until the fixtures and assertions exist.

**Step 3: Write minimal implementation**

Add fixtures for the initial vendor coverage wave and assert field normalization consistency. Use the first-wave vendor/command matrix defined in the design doc.

**Step 4: Run test to verify it passes**

Run: `pytest services/agent/tests/test_textfsm_parser.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add services/agent/tests/fixtures/textfsm services/agent/tests/test_textfsm_parser.py
git commit -m "test(agent): add TextFSM vendor coverage fixtures"
```

### Task 6: Add integration coverage for the full pipeline

**Files:**
- Create: `services/agent/tests/test_textfsm_pipeline_integration.py`
- Modify: `services/agent/pyproject.toml` or test config if needed

**Step 1: Write the failing test**

```python
def test_full_normalization_pipeline_produces_upload_ready_payload():
    ...
```

**Step 2: Run test to verify it fails**

Run: `pytest services/agent/tests/test_textfsm_pipeline_integration.py -v`
Expected: FAIL until the integration path is wired.

**Step 3: Write minimal implementation**

Exercise the normalize → sanitize → schema-validate sequence end to end. Include contract version compatibility checks and fallback-path assertions.

**Step 4: Run test to verify it passes**

Run: `pytest services/agent/tests/test_textfsm_pipeline_integration.py -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add services/agent/tests/test_textfsm_pipeline_integration.py services/agent/pyproject.toml
git commit -m "test(agent): add TextFSM pipeline integration coverage"
```

### Task 7: Update documentation and operational notes

**Files:**
- Modify: `docs/TODO.md`
- Modify: `/tmp/claw-memory/current-state.md`
- Modify: `/tmp/claw-memory/TODO.md`

**Step 1: Write the failing test**

Not applicable.

**Step 2: Run verification**

Run: `git diff -- docs/TODO.md`
Expected: Show the new Group 5 planning note and completion references.

**Step 3: Write minimal implementation**

Mark the design and implementation docs as created, and note the normalization scope in claw-memory.

**Step 4: Run verification**

Run: `git diff -- /tmp/claw-memory/current-state.md /tmp/claw-memory/TODO.md docs/TODO.md`
Expected: Docs reflect completed planning work and upcoming implementation tasks.

**Step 5: Commit**

```bash
git add docs/TODO.md
git commit -m "docs: record TextFSM normalization plan"
```

### Task 8: Operational verification and branch flow

**Files:**
- None

**Step 1: Run the relevant tests**

Run:
```bash
make test
```

Expected: All relevant agent and API tests pass, or any existing failures are explicitly documented and isolated.

**Step 2: Check repo status**

Run:
```bash
git status --short
```

Expected: Only the intended plan/doc updates remain or the tree is clean after commit.

**Step 3: Validate branch flow**

Run:
```bash
git status --short
```

Expected: Working tree is clean or contains only intended changes ready for review. Do not push directly to `main`; finish on the feature branch and use the normal review flow.
