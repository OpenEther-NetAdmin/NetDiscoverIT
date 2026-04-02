"""
NLI integration tests.

Tests the full POST /api/v1/query pipeline with:
- Mocked Anthropic API (avoids real API cost and network dependency)
- Mocked sentence-transformers model (avoids 3s cold-start in CI)
- Real FastAPI routing, schema validation, auth middleware
- Mocked DB for device results (avoids needing populated vectors)
"""
import json
import pytest
import numpy as np
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient

# Fixed Anthropic response fixture
_CLAUDE_FIXTURE_TEXT = (
    "Three devices have Telnet enabled: access-sw-01, access-sw-02, and legacy-router-01. "
    "These are all in the branch site. Consider disabling Telnet and enabling SSH.\n"
    '{"confidence": 0.92, "query_type": "security", "source_device_ids": ["uuid-1", "uuid-2", "uuid-3"]}'
)


@pytest.fixture(autouse=True)
def mock_sentence_transformers():
    """Prevent sentence-transformers from loading the real model in tests."""
    mock_model = MagicMock()
    mock_model.encode.return_value = np.ones(768, dtype=np.float32)
    
    with patch("app.services.nli.intent_classifier.SentenceTransformer", return_value=mock_model):
        with patch("app.services.nli.intent_classifier._get_model", return_value=mock_model):
            # Reset the module-level cached model so tests get the mock
            import app.services.nli.intent_classifier as clf_module
            clf_module._MODEL = None
            
            def mock_encode(texts, **kwargs):
                if isinstance(texts, str):
                    return np.ones(768, dtype=np.float32)
                return np.ones((len(texts), 768), dtype=np.float32)
            mock_model.encode.side_effect = mock_encode
            
            yield
            clf_module._MODEL = None


@pytest.fixture(autouse=True)
def mock_anthropic():
    """Mock Anthropic API to return the fixture response."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=_CLAUDE_FIXTURE_TEXT)]
    mock_client_instance = AsyncMock()
    mock_client_instance.messages.create = AsyncMock(return_value=mock_msg)
    with patch("app.services.nli.claude_synthesizer.AsyncAnthropic", return_value=mock_client_instance):
        # Reset cached NLI service so it picks up the mock
        import app.api.routes.nli as nli_route
        nli_route._nli_service = None
        yield
        nli_route._nli_service = None


@pytest.fixture
def mock_db_empty():
    """DB that returns no devices (simulates unpopulated vectors)."""
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db


@pytest.fixture
def mock_db_with_devices():
    """DB that returns two mock devices."""
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [
        MagicMock(
            id="uuid-1",
            hostname="access-sw-01",
            vendor="Cisco",
            device_type="switch",
            metadata={"security_posture": {"telnet_enabled": True, "ssh_enabled": False}},
            compliance_scope=["PCI-BOUNDARY"],
            similarity=0.94,
        ),
        MagicMock(
            id="uuid-2",
            hostname="access-sw-02",
            vendor="Cisco",
            device_type="switch",
            metadata={"security_posture": {"telnet_enabled": True, "ssh_enabled": False}},
            compliance_scope=[],
            similarity=0.89,
        ),
    ]
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db


class TestNLIRoute:
    def test_query_returns_200_and_valid_schema(self, client, mock_db_with_devices):
        """Full pipeline: security question → 200 with NLIResponse schema."""
        from app.api import dependencies
        from app.main import app

        app.dependency_overrides[dependencies.get_db] = lambda: mock_db_with_devices

        with patch("app.api.routes.nli.get_neo4j_client", return_value=None):
            with patch("app.core.config.settings.ANTHROPIC_API_KEY", "sk-test"):
                import app.api.routes.nli as nli_route
                nli_route._nli_service = None  # Force reinit with mock key
                response = client.post(
                    "/api/v1/query",
                    json={"question": "which devices have telnet enabled?"},
                )
                nli_route._nli_service = None

        app.dependency_overrides.pop(dependencies.get_db, None)

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "sources" in data
        assert "confidence" in data
        assert "query_type" in data
        assert "retrieved_device_count" in data
        assert "graph_traversal_used" in data
        assert isinstance(data["confidence"], float)
        assert 0.0 <= data["confidence"] <= 1.0

    def test_query_empty_question_returns_400(self, client):
        response = client.post("/api/v1/query", json={"question": ""})
        assert response.status_code == 400

    def test_query_unauthenticated_returns_401(self, app):
        """Without mocked auth, endpoint returns 401."""
        with TestClient(app) as raw_client:
            response = raw_client.post(
                "/api/v1/query",
                json={"question": "show me all devices"},
            )
        assert response.status_code == 401

    def test_query_no_api_key_returns_503(self, client, mock_db_empty):
        """When ANTHROPIC_API_KEY is empty, endpoint returns 503."""
        from app.api import dependencies
        from app.main import app
        import app.api.routes.nli as nli_route

        app.dependency_overrides[dependencies.get_db] = lambda: mock_db_empty
        nli_route._nli_service = None  # force re-init with no key

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}), \
             patch("app.core.config.settings.ANTHROPIC_API_KEY", ""), \
             patch("app.api.routes.nli.get_neo4j_client", return_value=None):
            # Temporarily init service with no key
            from app.services.nli.nli_service import NLIService
            with patch("app.services.nli.intent_classifier.SentenceTransformer"):
                nli_route._nli_service = NLIService(api_key="", model="claude-sonnet-4-6")
            response = client.post(
                "/api/v1/query",
                json={"question": "show all devices"},
            )

        app.dependency_overrides.pop(dependencies.get_db, None)
        nli_route._nli_service = None  # cleanup
        assert response.status_code == 503

    def test_query_with_no_devices_returns_answer_with_no_context(self, client, mock_db_empty):
        """When vectors are not populated (Group 6a not yet run), answer gracefully states no data."""
        from app.api import dependencies
        from app.main import app

        app.dependency_overrides[dependencies.get_db] = lambda: mock_db_empty

        with patch("app.api.routes.nli.get_neo4j_client", return_value=None):
            with patch("app.core.config.settings.ANTHROPIC_API_KEY", "sk-test"):
                import app.api.routes.nli as nli_route
                nli_route._nli_service = None  # Force reinit with mock key
                response = client.post(
                    "/api/v1/query",
                    json={"question": "which devices have telnet enabled?"},
                )
                nli_route._nli_service = None

        app.dependency_overrides.pop(dependencies.get_db, None)
        assert response.status_code == 200
        data = response.json()
        assert data["retrieved_device_count"] == 0
        assert data["graph_traversal_used"] is False

    def test_query_topology_question_attempts_graph_traversal(self, client, mock_db_with_devices):
        """Topology questions set graph_traversal_used=True when Neo4j is available."""
        from app.api import dependencies
        from app.main import app
        from app.services.nli.graph_traverser import GraphContext, QueryShape

        app.dependency_overrides[dependencies.get_db] = lambda: mock_db_with_devices

        mock_neo4j = MagicMock()

        with patch("app.api.routes.nli.get_neo4j_client", return_value=mock_neo4j), \
             patch("app.services.nli.graph_traverser.GraphTraverser.traverse",
                   new_callable=lambda: lambda self, **kw: AsyncMock(
                       return_value=GraphContext(
                           nodes=[{"hostname": "access-sw-01"}],
                           edges=[],
                           query_shape=QueryShape.NEIGHBORHOOD,
                       )
                   )()):
            with patch("app.core.config.settings.ANTHROPIC_API_KEY", "sk-test"):
                import app.api.routes.nli as nli_route
                nli_route._nli_service = None  # Force reinit with mock key
                response = client.post(
                    "/api/v1/query",
                    json={"question": "what connects to access-sw-01?"},
                )
                nli_route._nli_service = None

        app.dependency_overrides.pop(dependencies.get_db, None)
        assert response.status_code == 200
        assert response.json()["graph_traversal_used"] is True

    def test_top_k_clamped_to_20(self, client, mock_db_with_devices):
        """top_k > 20 is silently clamped."""
        from app.api import dependencies
        from app.main import app

        app.dependency_overrides[dependencies.get_db] = lambda: mock_db_with_devices

        with patch("app.api.routes.nli.get_neo4j_client", return_value=None):
            with patch("app.core.config.settings.ANTHROPIC_API_KEY", "sk-test"):
                import app.api.routes.nli as nli_route
                nli_route._nli_service = None  # Force reinit with mock key
                response = client.post(
                    "/api/v1/query",
                    json={"question": "which devices have telnet enabled?"},
                )
                nli_route._nli_service = None

        app.dependency_overrides.pop(dependencies.get_db, None)
        assert response.status_code == 200
