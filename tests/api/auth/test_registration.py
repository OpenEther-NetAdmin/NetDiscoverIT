"""
Tests for user registration - verifies Organization and User creation.

This test file verifies the fix for FK violation bug where registration
failed because User(organization_id=uuid4()) created a UUID but no Organization
row existed.
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select

from app.models.models import User, Organization


class TestRegistrationCreatesOrganization:
    """
    Test cases for registration creating both Organization and User.

    The bug: User registration created organization_id=uuid4() which generated
    a random UUID but no corresponding Organization row existed. The FK constraint
    fired on commit causing registration to fail.

    The fix: Create the Organization row FIRST, then use org.id as the foreign key.
    """

    @pytest.fixture
    def unique_email(self):
        return f"newuser-{uuid4().hex[:8]}@example.com"

    @pytest.mark.asyncio
    async def test_registration_creates_org_before_user(self, unique_email):
        """
        Verify that registration creates Organization row BEFORE creating User.

        This test mocks the database and captures what gets added to verify
        the order of operations: Organization is added first, then User.
        """
        added_objects = []
        flushed_objects = []

        mock_db = AsyncMock()
        mock_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
        mock_db.flush = AsyncMock(side_effect=lambda: flushed_objects.extend(added_objects))
        mock_db.commit = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.api.auth import register, UserCreate

        user_data = UserCreate(
            email=unique_email,
            password="SecurePassword123!",
            full_name="New Test User",
            role="viewer"
        )

        with patch("app.api.auth.dependencies.audit_log", new_callable=AsyncMock):
            with patch("app.api.auth.create_access_token") as mock_access:
                with patch("app.api.auth.create_refresh_token") as mock_refresh:
                    mock_access.return_value = "test_access_token"
                    mock_refresh.return_value = "test_refresh_token"

                    result = await register(user_data, mock_db)

        assert len(added_objects) == 2, "Should add exactly 2 objects: Organization and User"

        org_obj = added_objects[0]
        user_obj = added_objects[1]

        assert isinstance(org_obj, Organization), "First added object should be Organization"
        assert isinstance(user_obj, User), "Second added object should be User"
        assert user_obj.organization_id == org_obj.id, \
            "User.organization_id must match Organization.id (FK constraint)"

    @pytest.mark.asyncio
    async def test_registration_user_has_valid_org_reference(self, unique_email):
        """
        Verify that the created User has a valid organization_id that
        corresponds to an existing Organization.
        """
        added_objects = []

        mock_db = AsyncMock()
        mock_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.api.auth import register, UserCreate

        user_data = UserCreate(
            email=unique_email,
            password="SecurePassword123!",
            full_name="New Test User",
            role="admin"
        )

        with patch("app.api.auth.dependencies.audit_log", new_callable=AsyncMock):
            with patch("app.api.auth.create_access_token") as mock_access:
                with patch("app.api.auth.create_refresh_token") as mock_refresh:
                    mock_access.return_value = "test_token"
                    mock_refresh.return_value = "test_refresh"

                    await register(user_data, mock_db)

        org_obj = added_objects[0]
        user_obj = added_objects[1]

        assert org_obj.id is not None, "Organization must have an ID"
        assert user_obj.organization_id is not None, "User must have an organization_id"
        assert user_obj.organization_id == org_obj.id, \
            "User's organization_id must reference the created Organization's ID"

    @pytest.mark.asyncio
    async def test_registration_org_has_valid_slug(self, unique_email):
        """
        Verify that the created Organization has a properly formatted slug.
        """
        added_objects = []

        mock_db = AsyncMock()
        mock_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.api.auth import register, UserCreate

        user_data = UserCreate(
            email=unique_email,
            password="SecurePassword123!",
            full_name="New Test User",
        )

        with patch("app.api.auth.dependencies.audit_log", new_callable=AsyncMock):
            with patch("app.api.auth.create_access_token") as mock_access:
                with patch("app.api.auth.create_refresh_token") as mock_refresh:
                    mock_access.return_value = "test_token"
                    mock_refresh.return_value = "test_refresh"

                    await register(user_data, mock_db)

        org_obj = added_objects[0]

        assert org_obj.slug is not None, "Organization must have a slug"
        assert org_obj.slug.startswith("org-"), "Organization slug should start with 'org-'"


class TestRegistrationFKIntegrity:
    """
    Test that registration properly maintains FK integrity.

    The original bug: uuid4() was used for organization_id directly on User,
    creating a reference to a non-existent Organization row.
    """

    @pytest.fixture
    def unique_email(self):
        return f"fk-test-{uuid4().hex[:8]}@example.com"

    @pytest.mark.asyncio
    async def test_user_organization_id_is_valid_uuid(self, unique_email):
        """
        Verify User.organization_id is a valid UUID that matches an Organization.
        """
        added_objects = []

        mock_db = AsyncMock()
        mock_db.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        from app.api.auth import register, UserCreate

        user_data = UserCreate(
            email=unique_email,
            password="SecurePassword123!",
        )

        with patch("app.api.auth.dependencies.audit_log", new_callable=AsyncMock):
            with patch("app.api.auth.create_access_token") as mock_access:
                with patch("app.api.auth.create_refresh_token") as mock_refresh:
                    mock_access.return_value = "test_token"
                    mock_refresh.return_value = "test_refresh"

                    await register(user_data, mock_db)

        org_obj = added_objects[0]
        user_obj = added_objects[1]

        assert isinstance(org_obj.id, uuid4().__class__), "Organization ID should be UUID type"
        assert isinstance(user_obj.organization_id, uuid4().__class__), \
            "User.organization_id should be UUID type"
        assert str(user_obj.organization_id) == str(org_obj.id), \
            "User.organization_id must equal Organization.id"
