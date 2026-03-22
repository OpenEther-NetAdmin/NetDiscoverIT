import pytest
from pathlib import Path
from agent.sanitizer.config_sanitizer import ConfigSanitizer


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class TestSanitizerWithFixtures:
    @pytest.fixture
    def sanitizer(self):
        return ConfigSanitizer(org_id="test-org")

    def test_sanitize_cisco_ios_fixture(self, sanitizer):
        config = (FIXTURES_DIR / "cisco_ios_router.cfg").read_text()
        result = sanitizer.sanitize(config)

        assert "10.255.1.1" not in result["sanitized"]
        assert "10.1.1.1" not in result["sanitized"]
        assert "192.168.1.1" not in result["sanitized"]

        assert "Cisco123" not in result["sanitized"]
        assert "Operator456" not in result["sanitized"]

        assert "public" not in result["sanitized"]
        assert "private" not in result["sanitized"]

        assert "<ip_address>" in result["sanitized"]
        assert "<password>" in result["sanitized"]
        assert "<community_string>" in result["sanitized"]

        assert "interface" in result["sanitized"]
        assert "GigabitEthernet0/0" in result["sanitized"]
        assert "router ospf" in result["sanitized"]

    def test_sanitize_juniper_junos_fixture(self, sanitizer):
        config = (FIXTURES_DIR / "juniper_junos_router.cfg").read_text()
        result = sanitizer.sanitize(config)

        assert "10.1.1.1" not in result["sanitized"]
        assert "192.168.1.1" not in result["sanitized"]
        assert "8.8.8.8" not in result["sanitized"]

        assert "<ip_address>" in result["sanitized"]

    def test_redaction_map_completeness(self, sanitizer):
        config = (FIXTURES_DIR / "cisco_ios_router.cfg").read_text()
        result = sanitizer.sanitize(config)

        redaction_map = result["redaction_log"]
        assert redaction_map["org_id"] == "test-org"

        replacements = redaction_map["replacements"]
        assert len(replacements) > 0

        types = {r["type"] for r in replacements}
        assert "ipv4" in types or "password" in types or "community" in types

    def test_preserves_config_structure(self, sanitizer):
        config = (FIXTURES_DIR / "cisco_ios_router.cfg").read_text()
        result = sanitizer.sanitize(config)

        assert "hostname core-router-01" in result["sanitized"]
        assert "interface Loopback0" in result["sanitized"]
        assert "description Uplink to Core" in result["sanitized"]
        assert "!" in result["sanitized"]
        assert "end" in result["sanitized"]


class TestTierResolverWithFixtures:
    def test_tier2_used_for_structured_config(self):
        from agent.sanitizer import TierResolver, Tier

        resolver = TierResolver()
        config = (FIXTURES_DIR / "cisco_ios_router.cfg").read_text()

        tier = resolver.resolve(config, "cisco_ios")
        assert tier in [Tier.TIER_2, Tier.TIER_3]

    def test_tier3_used_for_unstructured_config(self):
        from agent.sanitizer import TierResolver, Tier

        resolver = TierResolver()
        config = "some random text without section headers"

        tier = resolver.resolve(config, "unknown")
        assert tier == Tier.TIER_3
