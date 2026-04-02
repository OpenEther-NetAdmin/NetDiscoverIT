"""
Tests for alerting API endpoints
"""

import pytest
from unittest.mock import AsyncMock
from uuid import uuid4


def test_list_alert_rules_empty(client):
    """Test listing alert rules when none exist returns empty list"""
    response = client.get("/api/v1/alerts/rules")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_list_alert_events_empty(client):
    """Test listing alert events when none exist returns empty list"""
    response = client.get("/api/v1/alerts/events")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_list_alert_rules_requires_auth(app):
    """Test that listing alert rules requires authentication"""
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        response = client.get("/api/v1/alerts/rules")
        assert response.status_code == 401


def test_list_alert_events_requires_auth(app):
    """Test that listing alert events requires authentication"""
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        response = client.get("/api/v1/alerts/events")
        assert response.status_code == 401


def test_get_alert_event_not_found(client):
    """Test getting a non-existent alert event returns 404"""
    fake_id = str(uuid4())
    response = client.get(f"/api/v1/alerts/events/{fake_id}")
    assert response.status_code == 404


def test_create_alert_rule(client):
    """Test creating a new alert rule"""
    alert_rule_data = {
        "name": "Test Alert Rule",
        "rule_type": "device_offline",
        "severity": "high",
        "conditions": {"threshold_minutes": 30},
        "is_enabled": True,
    }
    response = client.post("/api/v1/alerts/rules", json=alert_rule_data)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == alert_rule_data["name"]
    assert data["rule_type"] == alert_rule_data["rule_type"]


def test_update_alert_rule(client):
    """Test updating an existing alert rule"""
    alert_rule_data = {
        "name": "Original Name",
        "rule_type": "agent_offline",
        "severity": "medium",
        "conditions": {"threshold_minutes": 15},
        "is_enabled": True,
    }
    create_response = client.post("/api/v1/alerts/rules", json=alert_rule_data)
    assert create_response.status_code == 201
    rule_id = create_response.json()["id"]

    update_data = {"name": "Updated Name", "is_enabled": False}
    update_response = client.patch(f"/api/v1/alerts/rules/{rule_id}", json=update_data)
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["name"] == "Updated Name"
    assert data["is_enabled"] is False


def test_delete_alert_rule(client):
    """Test deleting an alert rule"""
    alert_rule_data = {
        "name": "Rule to Delete",
        "rule_type": "new_device",
        "severity": "low",
        "conditions": {},
        "is_enabled": True,
    }
    create_response = client.post("/api/v1/alerts/rules", json=alert_rule_data)
    assert create_response.status_code == 201
    rule_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/v1/alerts/rules/{rule_id}")
    assert delete_response.status_code == 204

    get_response = client.get(f"/api/v1/alerts/rules/{rule_id}")
    assert get_response.status_code == 404


def test_get_alert_rule_not_found(client):
    """Test getting a non-existent alert rule returns 404"""
    fake_id = str(uuid4())
    response = client.get(f"/api/v1/alerts/rules/{fake_id}")
    assert response.status_code == 404
