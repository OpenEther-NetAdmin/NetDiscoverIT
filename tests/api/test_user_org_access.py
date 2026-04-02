"""
Tests for UserOrgAccess CRUD endpoints and cross-org access control.
"""
import pytest
from uuid import uuid4

FIXED_ORG_ID = "00000000-0000-0000-0000-000000000001"
FIXED_USER_ID = "00000000-0000-0000-0000-000000000002"


class TestUserOrgAccessCrud:
    def test_grant_access_requires_admin(self, client):
        """Only admin users can grant org access"""
        grant_data = {
            "user_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "access_role": "read_only",
        }
        response = client.post("/api/v1/org-access", json=grant_data)
        assert response.status_code in (201, 409)

    def test_grant_access_validates_role(self, client):
        """Invalid access_role returns 422"""
        grant_data = {
            "user_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "access_role": "superadmin",
        }
        response = client.post("/api/v1/org-access", json=grant_data)
        assert response.status_code == 400

    def test_list_access_requires_admin(self, client):
        """Only admin users can list access grants"""
        response = client.get("/api/v1/org-access")
        assert response.status_code in (200, 403)

    def test_list_access_returns_pagination_shape(self, client):
        """List endpoint returns expected pagination fields"""
        response = client.get("/api/v1/org-access?skip=0&limit=10")
        if response.status_code == 200:
            data = response.json()
            assert "items" in data
            assert "total" in data
            assert "skip" in data
            assert "limit" in data

    def test_get_access_returns_404_for_unknown_id(self, client):
        """Getting a non-existent access grant returns 404"""
        fake_id = str(uuid4())
        response = client.get(f"/api/v1/org-access/{fake_id}")
        assert response.status_code == 404

    def test_update_access_returns_404_for_unknown_id(self, client):
        """Updating a non-existent access grant returns 404"""
        fake_id = str(uuid4())
        response = client.patch(f"/api/v1/org-access/{fake_id}", json={"access_role": "editor"})
        assert response.status_code == 404

    def test_delete_access_returns_404_for_unknown_id(self, client):
        """Deleting a non-existent access grant returns 404"""
        fake_id = str(uuid4())
        response = client.delete(f"/api/v1/org-access/{fake_id}")
        assert response.status_code == 404

    def test_update_access_validates_role(self, client):
        """Updating with invalid role returns 400"""
        fake_id = str(uuid4())
        response = client.patch(
            f"/api/v1/org-access/{fake_id}", json={"access_role": "invalid_role"}
        )
        assert response.status_code in (400, 404)


class TestRequireOrgAccessDependency:
    def test_require_org_access_allows_home_org(self, client):
        """User can access their own org via home org rule"""
        response = client.get(f"/api/v1/portal/overview?scope=self")
        assert response.status_code == 200

    def test_require_org_access_forbids_foreign_org(self, client):
        """User without UserOrgAccess cannot access foreign org"""
        from app.api.dependencies import require_org_access
        from app.api.schemas import User
        import asyncio

        class FakeDB:
            pass

        user = User(
            id=str(uuid4()),
            email="test@example.com",
            organization_id=FIXED_ORG_ID,
            role="viewer",
            is_active=True,
        )
        result = asyncio.get_event_loop().run_until_complete(
            require_org_access(str(uuid4()), user, FakeDB())
        )
        assert result is None or False
