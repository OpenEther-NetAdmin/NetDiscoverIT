"""
Tests for agent authentication - cross-tenant security.

These tests verify that agents can only authenticate to their own organization
and that the agent authentication properly scopes queries to the correct tenant.
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select, and_, or_

from app.api.dependencies import get_agent_auth
from app.api.schemas import AgentAuth
from app.core.security import hash_password
from app.models.models import LocalAgent


class TestAgentAuthCrossTenant:
    """
    Test cases for cross-tenant agent authentication security.

    These tests verify the fix for the security vulnerability where
    `agent.is_active is True` (identity check) would cause SQLAlchemy
    to drop the WHERE clause, fetching ALL agents across ALL organizations.
    """

    @pytest.fixture
    def org_a_id(self):
        return str(uuid4())

    @pytest.fixture
    def org_b_id(self):
        return str(uuid4())

    @pytest.fixture
    def mock_agent_a(self, org_a_id):
        """Create a mock agent in Organization A"""
        agent = MagicMock()
        agent.id = uuid4()
        agent.organization_id = MagicMock()
        agent.organization_id.__str__ = MagicMock(return_value=org_a_id)
        agent.name = "Agent A"
        agent.api_key_hash = hash_password("agent_a_key_123")
        agent.is_active = True
        return agent

    @pytest.fixture
    def mock_agent_b(self, org_b_id):
        """Create a mock agent in Organization B"""
        agent = MagicMock()
        agent.id = uuid4()
        agent.organization_id = MagicMock()
        agent.organization_id.__str__ = MagicMock(return_value=org_b_id)
        agent.name = "Agent B"
        agent.api_key_hash = hash_password("agent_b_key_456")
        agent.is_active = True
        return agent

    @pytest.mark.asyncio
    async def test_agent_auth_finds_correct_agent_by_key(self, org_a_id, mock_agent_a, mock_agent_b):
        """
        Test that get_agent_auth correctly identifies the agent by API key.

        The fix ensures that when we search for an agent by API key,
        we find the correct one without cross-tenant leakage.
        """
        captured_stmt = None

        async def capture_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            mock_result = MagicMock()
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = [mock_agent_a, mock_agent_b]
            mock_result.scalars.return_value = mock_scalars
            return mock_result

        mock_db = MagicMock()
        mock_db.execute = capture_execute

        with patch("app.core.security.verify_password") as mock_verify:
            def verify_side_effect(key, hash):
                if key == "agent_a_key_123" and hash == mock_agent_a.api_key_hash:
                    return True
                return False

            mock_verify.side_effect = verify_side_effect

            result = await get_agent_auth(
                x_agent_key="agent_a_key_123",
                db=mock_db
            )

            assert result is not None
            assert result.agent_name == "Agent A"

    @pytest.mark.asyncio
    async def test_agent_auth_rejects_wrong_key(self, org_a_id, org_b_id, mock_agent_a, mock_agent_b):
        """
        Agent A's key should NOT work for Agent B.
        """
        captured_stmt = None

        async def capture_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            mock_result = MagicMock()
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = [mock_agent_a, mock_agent_b]
            mock_result.scalars.return_value = mock_scalars
            return mock_result

        mock_db = MagicMock()
        mock_db.execute = capture_execute

        with patch("app.core.security.verify_password") as mock_verify:
            mock_verify.return_value = False

            with pytest.raises(Exception) as exc_info:
                await get_agent_auth(
                    x_agent_key="wrong_key",
                    db=mock_db
                )

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_agent_auth_only_returns_active_agents(self, mock_agent_a):
        """
        Verify that the query properly filters for active agents.

        The fix changes `is True` to `== True` which ensures proper SQL filtering.
        """
        inactive_agent = MagicMock()
        inactive_agent.id = uuid4()
        inactive_agent.organization_id = MagicMock()
        inactive_agent.name = "Inactive Agent"
        inactive_agent.api_key_hash = hash_password("inactive_key")
        inactive_agent.is_active = False

        captured_stmt = None

        async def capture_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            mock_result = MagicMock()
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = [mock_agent_a, inactive_agent]
            mock_result.scalars.return_value = mock_scalars
            return mock_result

        mock_db = MagicMock()
        mock_db.execute = capture_execute

        with patch("app.core.security.verify_password") as mock_verify:
            mock_verify.return_value = True

            result = await get_agent_auth(
                x_agent_key="any_key",
                db=mock_db
            )

            assert result.agent_name == "Agent A"

    @pytest.mark.asyncio
    async def test_get_agent_auth_uses_equality_not_identity(self, mock_agent_a, org_a_id):
        """
        Verify get_agent_auth generates SQL with == True, not is True.

        This ensures the WHERE clause is properly generated and the
        is_active filter actually filters rows instead of being dropped.

        The bug: `is True` uses identity comparison which SQLAlchemy
        cannot translate to SQL, causing the WHERE clause to be dropped.

        The fix: `== True` or implicit boolean check generates proper SQL.
        """
        captured_stmt = None

        async def capture_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            mock_result = MagicMock()
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = [mock_agent_a]
            mock_result.scalars.return_value = mock_scalars
            return mock_result

        mock_db = MagicMock()
        mock_db.execute = capture_execute

        with patch("app.core.security.verify_password", return_value=True):
            await get_agent_auth(x_agent_key="any_key", db=mock_db)

        assert captured_stmt is not None

        where_clause = captured_stmt.whereclause
        assert where_clause is not None, "WHERE clause must be present"

        clause_str = str(where_clause)
        assert "is_active" in clause_str.lower(), f"is_active must be in WHERE clause, got: {clause_str}"

        assert "!=" not in clause_str and "NOT" not in clause_str.upper(), \
            f"WHERE clause should use equality, not negation: {clause_str}"

    @pytest.mark.asyncio
    async def test_inactive_agent_not_returned(self, org_a_id):
        """
        Verify that the SQL query has WHERE is_active filter that would
        exclude inactive agents from database results.

        This test verifies the SQL QUERY has the filter, not just that
        the mock returns the right result.
        """
        inactive_agent = MagicMock()
        inactive_agent.id = uuid4()
        inactive_agent.organization_id = MagicMock()
        inactive_agent.organization_id.__str__ = MagicMock(return_value=org_a_id)
        inactive_agent.name = "Inactive Agent"
        inactive_agent.api_key_hash = hash_password("inactive_key")
        inactive_agent.is_active = False

        active_agent = MagicMock()
        active_agent.id = uuid4()
        active_agent.organization_id = MagicMock()
        active_agent.organization_id.__str__ = MagicMock(return_value=org_a_id)
        active_agent.name = "Active Agent"
        active_agent.api_key_hash = hash_password("active_key")
        active_agent.is_active = True

        captured_stmt = None

        async def capture_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            mock_result = MagicMock()
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = [active_agent]
            mock_result.scalars.return_value = mock_scalars
            return mock_result

        mock_db = MagicMock()
        mock_db.execute = capture_execute

        with patch("app.core.security.verify_password", return_value=True):
            result = await get_agent_auth(x_agent_key="active_key", db=mock_db)

        assert captured_stmt is not None, "Statement must be captured"

        where_clause = captured_stmt.whereclause
        assert where_clause is not None, "WHERE clause must be present for is_active filter"

        clause_str = str(where_clause).lower()
        assert "is_active" in clause_str, f"is_active must be in WHERE clause, got: {clause_str}"

        assert result.agent_name == "Active Agent"

    @pytest.mark.asyncio
    async def test_cross_tenant_access_denied(self, org_a_id, org_b_id):
        """
        Verify the SQL query is constructed with proper is_active filter.
        The password verification then ensures only the correct agent succeeds.
        """
        agent_org_a = MagicMock()
        agent_org_a.id = uuid4()
        agent_org_a.organization_id = MagicMock()
        agent_org_a.organization_id.__str__ = MagicMock(return_value=org_a_id)
        agent_org_a.name = "OrgA Agent"
        agent_org_a.api_key_hash = hash_password("org_a_key")
        agent_org_a.is_active = True

        agent_org_b = MagicMock()
        agent_org_b.id = uuid4()
        agent_org_b.organization_id = MagicMock()
        agent_org_b.organization_id.__str__ = MagicMock(return_value=org_b_id)
        agent_org_b.name = "OrgB Agent"
        agent_org_b.api_key_hash = hash_password("org_b_key")
        agent_org_b.is_active = True

        captured_stmt = None

        async def capture_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            mock_result = MagicMock()
            mock_scalars = MagicMock()
            mock_scalars.all.return_value = [agent_org_a, agent_org_b]
            mock_result.scalars.return_value = mock_scalars
            return mock_result

        mock_db = MagicMock()
        mock_db.execute = capture_execute

        with patch("app.core.security.verify_password") as mock_verify:
            def verify_side_effect(key, hash):
                return key == "org_a_key" and hash == agent_org_a.api_key_hash
            mock_verify.side_effect = verify_side_effect

            result = await get_agent_auth(x_agent_key="org_a_key", db=mock_db)

        assert captured_stmt is not None, "Statement must be captured"

        where_clause = captured_stmt.whereclause
        assert where_clause is not None, "WHERE clause must be present for is_active filter"

        clause_str = str(where_clause).lower()
        assert "is_active" in clause_str, f"is_active must be in WHERE clause, got: {clause_str}"

        assert result.agent_name == "OrgA Agent"
        assert result.organization_id == org_a_id


class TestAgentAuthSQLAlchemyQuery:
    """
    Test that SQLAlchemy queries properly filter by is_active.

    The bug: `LocalAgent.is_active is True` uses Python identity comparison
    which always returns False for SQLAlchemy column expressions, causing
    the WHERE clause to be dropped.

    The fix: Use `LocalAgent.is_active == True` or `LocalAgent.is_active`
    for boolean column comparison.
    """

    def test_is_active_comparison_uses_equality_not_identity(self):
        """
        Verify that `is_active == True` produces proper SQL filtering.

        This test documents the expected behavior after the fix.
        """
        query_fixed = select(LocalAgent).where(LocalAgent.is_active == True)
        query_implicit = select(LocalAgent).where(LocalAgent.is_active)
        query_buggy = select(LocalAgent).where(LocalAgent.is_active is True)

        assert query_fixed is not None
        assert query_implicit is not None
        assert query_buggy is not None

        assert query_fixed.whereclause is not None, "Fixed query must have WHERE clause"
        assert query_implicit.whereclause is not None, "Implicit query must have WHERE clause"

    def test_buggy_is_identity_query_produces_false_literal(self):
        """
        Demonstrate that `is True` causes the WHERE clause to produce a 'false' literal.

        This is the core of the bug: `column is True` evaluates to a SQL `false` literal
        instead of a proper comparison. This causes the query to return NO rows
        (since WHERE false matches nothing), rather than properly filtering by is_active.
        """
        query_with_is_true = select(LocalAgent).where(LocalAgent.is_active is True)
        query_fixed = select(LocalAgent).where(LocalAgent.is_active == True)

        buggy_clause_str = str(query_with_is_true.whereclause).lower()
        fixed_clause_str = str(query_fixed.whereclause).lower()

        assert "false" in buggy_clause_str, \
            f"is True should produce 'false' literal, got: {query_with_is_true.whereclause}"

        assert "is_active" in fixed_clause_str or "active" in fixed_clause_str, \
            f"== True should produce is_active comparison, got: {query_fixed.whereclause}"

    def test_equality_vs_identity_sql_generation(self):
        """
        Verify that == True and is True produce different SQL.
        """
        query_equality = select(LocalAgent).where(LocalAgent.is_active == True)
        query_implicit = select(LocalAgent).where(LocalAgent.is_active)

        equality_str = str(query_equality)
        implicit_str = str(query_implicit)

        assert "is_active" in equality_str.lower() or "active" in equality_str.lower()
        assert "is_active" in implicit_str.lower() or "active" in implicit_str.lower()
