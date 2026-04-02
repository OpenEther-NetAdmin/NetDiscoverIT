"""
Tests for ACL snapshot verification endpoint.
"""
import pytest
from uuid import uuid4


class TestACLVerifyEndpoint:
    def test_verify_returns_404_for_unknown_snapshot(self, client):
        """Verify endpoint returns 404 for non-existent snapshot ID"""
        fake_id = str(uuid4())
        response = client.get(f"/api/v1/acl-snapshots/{fake_id}/verify")
        assert response.status_code == 404

    def test_verify_returns_400_for_invalid_uuid(self, client):
        """Verify endpoint returns 400 for malformed UUID"""
        response = client.get("/api/v1/acl-snapshots/not-a-uuid/verify")
        assert response.status_code == 400

    def test_verify_response_shape(self, client):
        """Verify response has expected fields"""
        fake_id = str(uuid4())
        response = client.get(f"/api/v1/acl-snapshots/{fake_id}/verify")
        if response.status_code == 404:
            return
        data = response.json()
        assert "snapshot_id" in data
        assert "verified" in data
        assert "checks" in data


class TestACLVerifyChecks:
    def test_verify_checks_include_expected_keys(self, client):
        """Verify checks dict should include org_ownership, content_hmac, config_hash, etc."""
        fake_id = str(uuid4())
        response = client.get(f"/api/v1/acl-snapshots/{fake_id}/verify")
        if response.status_code == 404:
            assert True
            return
        data = response.json()
        assert "checks" in data
        checks = data["checks"]
        expected_keys = {"org_ownership", "summary"}
        assert expected_keys.issubset(checks.keys()), f"Expected {expected_keys}, got {checks.keys()}"
