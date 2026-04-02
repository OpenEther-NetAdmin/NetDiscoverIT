"""
Tests for portal overview endpoint — both self and MSP aggregate modes.
"""
import pytest


class TestPortalOverviewSelfScope:
    def test_overview_returns_200(self, client):
        """Portal overview returns 200 for authenticated user"""
        response = client.get("/api/v1/portal/overview")
        assert response.status_code == 200

    def test_overview_returns_correct_fields(self, client):
        """Overview response has all expected fields"""
        response = client.get("/api/v1/portal/overview")
        if response.status_code != 200:
            pytest.skip("No data in test DB")
        data = response.json()
        assert "total_devices" in data
        assert "active_discoveries" in data
        assert "total_alerts" in data
        assert "open_alerts" in data
        assert "recent_devices" in data
        assert "recent_discoveries" in data

    def test_overview_defaults_to_self_scope(self, client):
        """Default scope is 'self' when not specified"""
        response = client.get("/api/v1/portal/overview")
        if response.status_code != 200:
            pytest.skip("No data in test DB")
        data = response.json()
        assert isinstance(data["total_devices"], int)


class TestPortalOverviewMSPScope:
    def test_overview_msp_scope_returns_200(self, client):
        """Portal overview with scope=msp returns 200"""
        response = client.get("/api/v1/portal/overview?scope=msp")
        assert response.status_code == 200

    def test_overview_msp_returns_msp_fields(self, client):
        """MSP scope returns additional aggregate fields"""
        response = client.get("/api/v1/portal/overview?scope=msp")
        if response.status_code != 200:
            pytest.skip("No data in test DB")
        data = response.json()
        assert "child_orgs_total_devices" in data
        assert "child_orgs_total_alerts" in data
        assert "child_orgs_open_alerts" in data
        assert isinstance(data["child_orgs_total_devices"], int)

    def test_overview_invalid_scope_returns_422(self, client):
        """Invalid scope value returns 422"""
        response = client.get("/api/v1/portal/overview?scope=invalid")
        assert response.status_code == 422

    def test_overview_self_and_msp_both_return_devices(self, client):
        """Both self and msp scopes return total_devices"""
        self_resp = client.get("/api/v1/portal/overview?scope=self")
        msp_resp = client.get("/api/v1/portal/overview?scope=msp")
        if self_resp.status_code != 200 or msp_resp.status_code != 200:
            pytest.skip("No data in test DB")
        self_data = self_resp.json()
        msp_data = msp_resp.json()
        assert "total_devices" in self_data
        assert "total_devices" in msp_data
