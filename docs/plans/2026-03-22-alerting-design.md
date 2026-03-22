# Alerting Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add core alerting for config drift, rule evaluation, agent offline detection, and extensible integration routing with API endpoints to inspect alert rules and alert events.

**Architecture:** Alert generation stays in Celery tasks so collection and evaluation can run on a schedule without blocking API requests. Alert routing is hybrid: the alert task creates the `AlertEvent` synchronously, then dispatches per-integration delivery jobs so retries, rate limits, and failures are isolated per destination. The design reuses the existing `AlertRule`, `AlertEvent`, `IntegrationConfig`, `ChangeRecord`, and `LocalAgent` models, and adds only the minimal schema and API surface needed to support alert inspection and persistence.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Celery, PostgreSQL JSONB, Slack webhook delivery, PagerDuty Events API

---

### Task 1: Add alerting schema migrations

**Files:**
- Modify: `services/api/alembic/versions/001_initial_migration.py`
- Create: `services/api/alembic/versions/003_add_alerting_tables.py`
- Test: `services/api/tests/api/test_alerting_migrations.py`

**Step 1: Write the failing test**

```python
def test_alerting_tables_exist(engine):
    inspector = sa.inspect(engine)
    assert "alert_rules" in inspector.get_table_names()
    assert "alert_events" in inspector.get_table_names()
```

**Step 2: Run the test to verify it fails**

Run: `pytest services/api/tests/api/test_alerting_migrations.py -v`

Expected: FAIL because the alerting tables are not yet created by migrations.

**Step 3: Write minimal migration changes**

Add Alembic DDL for `alert_rules` and `alert_events`, including indexes and foreign keys that match the existing SQLAlchemy models.

**Step 4: Run the test to verify it passes**

Run: `pytest services/api/tests/api/test_alerting_migrations.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add services/api/alembic/versions/001_initial_migration.py services/api/alembic/versions/003_add_alerting_tables.py services/api/tests/api/test_alerting_migrations.py
git commit -m "feat(api): add alerting schema migrations"
```

### Task 2: Add alerting API schemas and endpoints

**Files:**
- Modify: `services/api/app/api/schemas.py`
- Modify: `services/api/app/api/routes.py`
- Create: `services/api/tests/api/test_alerting_api.py`

**Step 1: Write the failing test**

```python
async def test_list_alert_events(client):
    response = await client.get("/api/v1/alerts/events")
    assert response.status_code == 200
```

**Step 2: Run the test to verify it fails**

Run: `pytest services/api/tests/api/test_alerting_api.py -v`

Expected: FAIL because the alert endpoints do not exist yet.

**Step 3: Write minimal implementation**

Add response/request schemas for alert rules and events, then add endpoints to list alert rules, list alert events, and retrieve alert event detail scoped to the current organization.

**Step 4: Run the test to verify it passes**

Run: `pytest services/api/tests/api/test_alerting_api.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add services/api/app/api/schemas.py services/api/app/api/routes.py services/api/tests/api/test_alerting_api.py
git commit -m "feat(api): expose alert inspection endpoints"
```

### Task 3: Implement config drift detection

**Files:**
- Create: `services/api/app/tasks/alerting.py`
- Modify: `services/api/app/models/models.py`
- Create: `services/api/tests/tasks/test_config_drift_alerts.py`

**Step 1: Write the failing test**

```python
async def test_config_drift_creates_alert_event(session):
    result = await detect_config_drift.delay(...)
    assert result.get() == "alert_created"
```

**Step 2: Run the test to verify it fails**

Run: `pytest services/api/tests/tasks/test_config_drift_alerts.py -v`

Expected: FAIL because the Celery task does not exist yet.

**Step 3: Write minimal implementation**

Implement a Celery task that compares an incoming `config_hash` against the latest `ChangeRecord` approval window for the device. If no approved change covers the hash transition, create an `AlertEvent` with `rule_type=config_drift` and record evidence in `details`.

**Step 4: Run the test to verify it passes**

Run: `pytest services/api/tests/tasks/test_config_drift_alerts.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add services/api/app/tasks/alerting.py services/api/app/models/models.py services/api/tests/tasks/test_config_drift_alerts.py
git commit -m "feat(alerting): detect unauthorized config drift"
```

### Task 4: Implement rule evaluation and agent offline detection

**Files:**
- Modify: `services/api/app/tasks/alerting.py`
- Create: `services/api/tests/tasks/test_alert_rule_eval.py`
- Create: `services/api/tests/tasks/test_agent_offline_alerts.py`

**Step 1: Write the failing tests**

```python
async def test_rule_evaluation_skips_disabled_rules(session):
    ...

async def test_agent_offline_creates_event(session):
    ...
```

**Step 2: Run the tests to verify they fail**

Run: `pytest services/api/tests/tasks/test_alert_rule_eval.py services/api/tests/tasks/test_agent_offline_alerts.py -v`

Expected: FAIL because the scheduled tasks do not exist yet.

**Step 3: Write minimal implementation**

Add a Celery beat task that loads enabled alert rules for the org(s) associated with the collection cycle and evaluates them once per cycle. Add a separate beat task that scans `LocalAgent.last_seen` against each rule threshold and emits `AlertEvent` records for agents that are stale.

**Step 4: Run the tests to verify they pass**

Run: `pytest services/api/tests/tasks/test_alert_rule_eval.py services/api/tests/tasks/test_agent_offline_alerts.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add services/api/app/tasks/alerting.py services/api/tests/tasks/test_alert_rule_eval.py services/api/tests/tasks/test_agent_offline_alerts.py
git commit -m "feat(alerting): add scheduled rule evaluation"
```

### Task 5: Implement alert routing adapters and delivery jobs

**Files:**
- Create: `services/api/app/tasks/alert_delivery.py`
- Create: `services/api/app/services/alert_routing.py`
- Create: `services/api/tests/tasks/test_alert_routing.py`

**Step 1: Write the failing test**

```python
async def test_alert_routes_to_enabled_integrations(session):
    ...
```

**Step 2: Run the test to verify it fails**

Run: `pytest services/api/tests/tasks/test_alert_routing.py -v`

Expected: FAIL because routing and delivery jobs do not exist yet.

**Step 3: Write minimal implementation**

Create a dispatcher that reads `notify_integration_ids`, resolves each `IntegrationConfig`, and enqueues one delivery task per integration. Implement Slack and PagerDuty adapters first, but keep the router generic so new integration types can be added without changing the dispatcher.

**Step 4: Run the test to verify it passes**

Run: `pytest services/api/tests/tasks/test_alert_routing.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add services/api/app/tasks/alert_delivery.py services/api/app/services/alert_routing.py services/api/tests/tasks/test_alert_routing.py
git commit -m "feat(alerting): route alert deliveries by integration"
```

### Task 6: Update task scheduling and verification

**Files:**
- Modify: `services/api/app/celery.py` or the existing Celery app module
- Modify: `services/api/app/tasks/alerting.py`
- Create: `services/api/tests/tasks/test_celery_schedule.py`

**Step 1: Write the failing test**

```python
def test_alert_tasks_registered(celery_app):
    assert "alerting.evaluate_rules" in celery_app.tasks
```

**Step 2: Run the test to verify it fails**

Run: `pytest services/api/tests/tasks/test_celery_schedule.py -v`

Expected: FAIL until the tasks are registered and beat schedule entries are added.

**Step 3: Write minimal implementation**

Register the new tasks and add beat schedule entries for rule evaluation and offline detection with conservative defaults.

**Step 4: Run the test to verify it passes**

Run: `pytest services/api/tests/tasks/test_celery_schedule.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add services/api/app/celery.py services/api/app/tasks/alerting.py services/api/tests/tasks/test_celery_schedule.py
git commit -m "feat(alerting): schedule alert evaluation tasks"
```

### Task 7: Verify end-to-end alerting behavior

**Files:**
- Test suite only

**Step 1: Run the focused alerting test set**

Run: `pytest services/api/tests/api/test_alerting_api.py services/api/tests/tasks/test_config_drift_alerts.py services/api/tests/tasks/test_alert_rule_eval.py services/api/tests/tasks/test_agent_offline_alerts.py services/api/tests/tasks/test_alert_routing.py services/api/tests/tasks/test_celery_schedule.py -v`

Expected: PASS.

**Step 2: Run the broader API test suite**

Run: `pytest services/api/tests/api -v`

Expected: PASS, aside from any known unrelated environment issues.

**Step 3: Commit any final fixes**

```bash
git add -A
git commit -m "test(alerting): verify alert pipeline coverage"
```
