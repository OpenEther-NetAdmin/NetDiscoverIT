"""
Unit tests for NLI service components.
All external dependencies (sentence-transformers, Anthropic, Neo4j) are mocked.
"""
import json
import pytest
from dataclasses import dataclass
from unittest.mock import MagicMock, AsyncMock, patch
import numpy as np


# ---------------------------------------------------------------------------
# IntentClassifier tests
# ---------------------------------------------------------------------------

class TestIntentClassifier:
    def _make_classifier(self, mock_model=None):
        """Return an IntentClassifier with the sentence-transformers model mocked."""
        with patch("app.services.nli.intent_classifier.SentenceTransformer") as MockST:
            if mock_model is None:
                mock_model = MagicMock()
                # encode() returns a 2D array if list is passed, or 1D if string
                def mock_encode(texts, **kwargs):
                    if isinstance(texts, str):
                        return np.ones(768, dtype=np.float32)
                    return np.ones((len(texts), 768), dtype=np.float32)
                mock_model.encode.side_effect = mock_encode
            MockST.return_value = mock_model
            from app.services.nli.intent_classifier import IntentClassifier
            return IntentClassifier()

    def test_topology_keywords_set_needs_graph(self):
        clf = self._make_classifier()
        intent = clf.classify("what connects to core-router-01?")
        assert intent.needs_graph is True

    def test_path_keyword_sets_needs_graph(self):
        clf = self._make_classifier()
        intent = clf.classify("show me the path from host-a to firewall-b")
        assert intent.needs_graph is True

    def test_security_question_no_graph(self):
        clf = self._make_classifier()
        intent = clf.classify("which devices have telnet enabled?")
        assert intent.needs_graph is False

    def test_ambiguous_question_uses_all_domains(self):
        """When no domain clears the similarity threshold, all 4 domains are selected."""
        mock_model = MagicMock()
        def mock_encode(texts, **kwargs):
            if isinstance(texts, str):
                return np.zeros(768, dtype=np.float32)
            return np.ones((len(texts), 768), dtype=np.float32)
        mock_model.encode.side_effect = mock_encode
        clf = self._make_classifier(mock_model)
        intent = clf.classify("xyzzy frobulate the snorkel")
        assert len(intent.domains) == 5

    def test_extracted_entities_captures_ip(self):
        clf = self._make_classifier()
        intent = clf.classify("what connects to 192.168.1.1?")
        assert "192.168.1.1" in intent.extracted_entities

    def test_extracted_entities_captures_hostname(self):
        clf = self._make_classifier()
        intent = clf.classify("show neighbors of core-router-01")
        assert "core-router-01" in intent.extracted_entities


# ---------------------------------------------------------------------------
# VectorRetriever tests
# ---------------------------------------------------------------------------

class TestVectorRetriever:
    def _make_retriever(self):
        from app.services.nli.vector_retriever import VectorRetriever
        return VectorRetriever()

    def test_domain_to_column_mapping(self):
        from app.services.nli.vector_retriever import DOMAIN_COLUMN_MAP
        assert DOMAIN_COLUMN_MAP["topology"] == "topology_vector"
        assert DOMAIN_COLUMN_MAP["security"] == "security_vector"
        assert DOMAIN_COLUMN_MAP["compliance"] == "role_vector"
        assert DOMAIN_COLUMN_MAP["changes"] == "config_vector"
        assert DOMAIN_COLUMN_MAP["inventory"] == "role_vector"

    def test_top_k_clamped_to_20(self):
        from app.services.nli.vector_retriever import VectorRetriever
        r = VectorRetriever()
        assert r._clamp_top_k(100) == 20
        assert r._clamp_top_k(5) == 5
        assert r._clamp_top_k(0) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_vectors(self):
        """Devices with NULL vectors return empty results (graceful Group 6a degradation)."""
        from app.services.nli.vector_retriever import VectorRetriever, DeviceContext
        r = VectorRetriever()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        import numpy as np
        results = await r.retrieve(
            db=mock_db,
            org_id="00000000-0000-0000-0000-000000000001",
            domain="security",
            query_vec=np.ones(768, dtype=np.float32),
            top_k=5,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_device_context_on_match(self):
        from app.services.nli.vector_retriever import VectorRetriever, DeviceContext
        r = VectorRetriever()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            MagicMock(
                id="uuid-1",
                hostname="core-router-01",
                vendor="Cisco",
                device_type="router",
                metadata={"security_posture": {"ssh_enabled": True, "telnet_enabled": False}},
                compliance_scope=["PCI-BOUNDARY"],
                similarity=0.91,
            )
        ]
        mock_db.execute = AsyncMock(return_value=mock_result)

        import numpy as np
        results = await r.retrieve(
            db=mock_db,
            org_id="00000000-0000-0000-0000-000000000001",
            domain="security",
            query_vec=np.ones(768, dtype=np.float32),
            top_k=5,
        )
        assert len(results) == 1
        assert results[0].device_id == "uuid-1"
        assert results[0].hostname == "core-router-01"
        assert results[0].similarity == pytest.approx(0.91)


# ---------------------------------------------------------------------------
# GraphTraverser tests
# ---------------------------------------------------------------------------

class TestGraphTraverser:
    def _make_traverser(self):
        from app.services.nli.graph_traverser import GraphTraverser
        return GraphTraverser()

    def test_neighborhood_shape_selected_for_connects_to(self):
        from app.services.nli.graph_traverser import GraphTraverser, QueryShape
        t = GraphTraverser()
        shape = t._detect_shape("what connects to core-router-01?")
        assert shape == QueryShape.NEIGHBORHOOD

    def test_path_shape_selected_for_path_from(self):
        from app.services.nli.graph_traverser import GraphTraverser, QueryShape
        t = GraphTraverser()
        shape = t._detect_shape("show path from host-a to firewall-b")
        assert shape == QueryShape.PATH

    def test_vlan_shape_selected_for_segment_keywords(self):
        from app.services.nli.graph_traverser import GraphTraverser, QueryShape
        t = GraphTraverser()
        shape = t._detect_shape("what devices are in the same VLAN as core-sw-01?")
        assert shape == QueryShape.VLAN

    def test_neighborhood_is_default_shape(self):
        from app.services.nli.graph_traverser import GraphTraverser, QueryShape
        t = GraphTraverser()
        shape = t._detect_shape("what is upstream of this device")
        assert shape == QueryShape.NEIGHBORHOOD

    @pytest.mark.asyncio
    async def test_returns_none_when_neo4j_unavailable(self):
        from app.services.nli.graph_traverser import GraphTraverser
        from app.services.nli.vector_retriever import DeviceContext
        t = GraphTraverser()

        # No Neo4j client provided
        result = await t.traverse(
            neo4j_client=None,
            question="what connects to core-router-01?",
            anchor_devices=[
                DeviceContext(
                    device_id="uuid-1",
                    hostname="core-router-01",
                    vendor="Cisco",
                    device_type="router",
                    metadata={},
                    compliance_scope=[],
                    similarity=0.91,
                )
            ],
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_neo4j_exception(self):
        from app.services.nli.graph_traverser import GraphTraverser
        from app.services.nli.vector_retriever import DeviceContext
        t = GraphTraverser()

        mock_client = AsyncMock()
        # The graph_traverser code we implement will call methods on _driver.session(), so let's mock the traverse itself failing
        mock_client._driver = MagicMock()
        mock_client._driver.session.side_effect = RuntimeError("connection refused")

        result = await t.traverse(
            neo4j_client=mock_client,
            question="what connects to core-router-01?",
            anchor_devices=[
                DeviceContext(
                    device_id="uuid-1",
                    hostname="core-router-01",
                    vendor="Cisco",
                    device_type="router",
                    metadata={},
                    compliance_scope=[],
                    similarity=0.91,
                )
            ],
        )
        assert result is None


# ---------------------------------------------------------------------------
# ContextBuilder tests
# ---------------------------------------------------------------------------

class TestContextBuilder:
    def _make_builder(self):
        from app.services.nli.context_builder import ContextBuilder
        return ContextBuilder()

    def _make_device(self, hostname="core-router-01", similarity=0.91):
        from app.services.nli.vector_retriever import DeviceContext
        return DeviceContext(
            device_id="uuid-1",
            hostname=hostname,
            vendor="Cisco",
            device_type="router",
            metadata={
                "security_posture": {
                    "ssh_enabled": True,
                    "telnet_enabled": False,
                    "http_enabled": False,
                    "snmp_enabled": True,
                },
                "inferred_role": "core_router",
                "role_confidence": 0.95,
            },
            compliance_scope=["PCI-BOUNDARY"],
            similarity=similarity,
        )

    def test_builds_non_empty_context(self):
        builder = self._make_builder()
        context, sources = builder.build([self._make_device()], None)
        assert len(context) > 0
        assert "core-router-01" in context

    def test_sources_list_populated(self):
        builder = self._make_builder()
        _, sources = builder.build([self._make_device()], None)
        assert len(sources) == 1
        assert sources[0].device_id == "uuid-1"
        assert sources[0].hostname == "core-router-01"
        assert sources[0].similarity == pytest.approx(0.91)

    def test_empty_devices_returns_no_context_found(self):
        builder = self._make_builder()
        context, sources = builder.build([], None)
        assert "no matching devices" in context.lower()
        assert sources == []

    def test_graph_context_included_when_provided(self):
        from app.services.nli.graph_traverser import GraphContext, QueryShape
        builder = self._make_builder()
        graph = GraphContext(
            nodes=[{"hostname": "core-router-01"}, {"hostname": "edge-fw-01"}],
            edges=[{"type": "CONNECTED_TO", "start": "core-router-01", "end": "edge-fw-01"}],
            query_shape=QueryShape.NEIGHBORHOOD,
        )
        context, _ = builder.build([self._make_device()], graph)
        assert "TOPOLOGY" in context
        assert "edge-fw-01" in context

    def test_token_count_under_budget(self):
        builder = self._make_builder()
        # 20 devices should still fit under 8k tokens
        devices = [self._make_device(hostname=f"sw-{i:02d}", similarity=0.9 - i * 0.01) for i in range(20)]
        context, _ = builder.build(devices, None)
        token_count = builder._count_tokens(context)
        assert token_count <= 8000

# ---------------------------------------------------------------------------
# ClaudeSynthesizer tests
# ---------------------------------------------------------------------------

class TestClaudeSynthesizer:
    def _make_synthesizer(self, api_key="test-key"):
        with patch("app.services.nli.claude_synthesizer.AsyncAnthropic"):
            from app.services.nli.claude_synthesizer import ClaudeSynthesizer
            return ClaudeSynthesizer(api_key=api_key, model="claude-sonnet-4-6")

    def test_available_false_when_no_api_key(self):
        from app.services.nli.claude_synthesizer import ClaudeSynthesizer
        with patch("app.services.nli.claude_synthesizer.AsyncAnthropic"):
            s = ClaudeSynthesizer(api_key="", model="claude-sonnet-4-6")
        assert s.available is False

    def test_available_true_when_api_key_set(self):
        s = self._make_synthesizer(api_key="sk-ant-test")
        assert s.available is True

    def test_parse_confidence_json_valid(self):
        s = self._make_synthesizer()
        answer, confidence, query_type, source_ids = s._parse_response(
            'Three devices have Telnet enabled.\n'
            '{"confidence": 0.92, "query_type": "security", "source_device_ids": ["uuid-1", "uuid-2"]}'
        )
        assert answer == "Three devices have Telnet enabled."
        assert confidence == pytest.approx(0.92)
        assert query_type == "security"
        assert source_ids == ["uuid-1", "uuid-2"]

    def test_parse_confidence_json_malformed_falls_back(self):
        s = self._make_synthesizer()
        answer, confidence, query_type, source_ids = s._parse_response(
            "Some answer without a JSON block."
        )
        assert answer == "Some answer without a JSON block."
        assert confidence == pytest.approx(0.5)
        assert query_type == "inventory"
        assert source_ids == []

    def test_parse_confidence_clamped_to_0_1(self):
        s = self._make_synthesizer()
        _, confidence, _, _ = s._parse_response(
            'Answer.\n{"confidence": 1.5, "query_type": "security", "source_device_ids": []}'
        )
        assert confidence <= 1.0

    @pytest.mark.asyncio
    async def test_synthesize_calls_anthropic_and_returns_parsed(self):
        with patch("app.services.nli.claude_synthesizer.AsyncAnthropic") as MockClient:
            mock_instance = AsyncMock()
            mock_create = AsyncMock(return_value=MagicMock(
                content=[MagicMock(text=(
                    'Three devices have Telnet enabled: sw-01, sw-02, sw-03.\n'
                    '{"confidence": 0.90, "query_type": "security", "source_device_ids": ["uuid-1"]}'
                ))]
            ))
            mock_instance.messages.create = mock_create
            MockClient.return_value = mock_instance

            from importlib import reload
            import app.services.nli.claude_synthesizer as cs_module
            reload(cs_module)
            
            with patch.object(cs_module, "AsyncAnthropic", MockClient):
                synth = cs_module.ClaudeSynthesizer(api_key="sk-test", model="claude-sonnet-4-6")

                result = await synth.synthesize(
                    question="Which devices have Telnet?",
                    context="=== NETWORK CONTEXT ===\nDevice: sw-01\n...",
                )

        assert "Telnet" in result.answer
        assert result.confidence == pytest.approx(0.90)
        assert result.query_type == "security"

# ---------------------------------------------------------------------------
# NLIService orchestrator tests
# ---------------------------------------------------------------------------

class TestNLIService:
    def _make_service(self, api_key="sk-test"):
        with patch("app.services.nli.intent_classifier.SentenceTransformer"), \
             patch("app.services.nli.claude_synthesizer.AsyncAnthropic"):
            from app.services.nli.nli_service import NLIService
            return NLIService(api_key=api_key, model="claude-sonnet-4-6")

    def test_service_unavailable_when_no_api_key(self):
        with patch("app.services.nli.intent_classifier.SentenceTransformer"), \
             patch("app.services.nli.claude_synthesizer.AsyncAnthropic"):
            from app.services.nli.nli_service import NLIService
            svc = NLIService(api_key="", model="claude-sonnet-4-6")
        assert svc.available is False

    def test_service_available_when_api_key_set(self):
        svc = self._make_service()
        assert svc.available is True

    @pytest.mark.asyncio
    async def test_query_returns_nli_response(self):
        from app.services.nli.nli_service import NLIService
        from app.api.schemas import NLIResponse

        # We need to mock _get_model in intent_classifier for the local import inside query()
        with patch("app.services.nli.intent_classifier._get_model") as MockGetModel, \
             patch("app.services.nli.intent_classifier.SentenceTransformer") as MockST, \
             patch("app.services.nli.claude_synthesizer.AsyncAnthropic"):
            mock_model = MagicMock()
            def mock_encode(texts, **kwargs):
                if isinstance(texts, str):
                    return np.ones(768, dtype=np.float32)
                return np.ones((len(texts), 768), dtype=np.float32)
            mock_model.encode.side_effect = mock_encode
            MockGetModel.return_value = mock_model
            MockST.return_value = mock_model
            
            svc = NLIService(api_key="sk-test", model="claude-sonnet-4-6")

            mock_db = AsyncMock()
            # VectorRetriever returns empty (no vectors populated — graceful degradation)
            mock_result = MagicMock()
            mock_result.fetchall.return_value = []
            mock_db.execute = AsyncMock(return_value=mock_result)

            # Patch ClaudeSynthesizer.synthesize
            from app.services.nli.claude_synthesizer import SynthesisResult
            svc._synthesizer.synthesize = AsyncMock(return_value=SynthesisResult(
                answer="No matching devices found in the network database.",
                confidence=0.1,
                query_type="inventory",
                source_device_ids=[],
            ))

            result = await svc.query(
                db=mock_db,
                neo4j_client=None,
                question="which devices have telnet enabled?",
                org_id="00000000-0000-0000-0000-000000000001",
                top_k=5,
            )
        assert isinstance(result, NLIResponse)
        assert result.answer is not None
        assert 0.0 <= result.confidence <= 1.0
        assert result.graph_traversal_used is False
