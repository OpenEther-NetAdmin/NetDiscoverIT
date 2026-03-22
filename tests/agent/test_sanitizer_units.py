import pytest
from agent.sanitizer.token_mapper import TokenMapper, TokenType
from agent.sanitizer.redaction_logger import RedactionLogger, HASH_TRUNCATION
from agent.sanitizer.tier_resolver import TierResolver, Tier
from agent.sanitizer.tiers.tier2_section import SectionRegexSanitizer
from agent.sanitizer.tiers.tier3_regex import AggressiveRegexSanitizer


class TestTokenMapper:
    def test_default_tokens(self):
        mapper = TokenMapper()
        assert mapper.get_token(TokenType.IPV4) == "<ip_address>"
        assert mapper.get_token(TokenType.PASSWORD) == "<password>"
        assert mapper.get_token("unknown") == "<unknown>"

    def test_custom_tokens(self):
        mapper = TokenMapper(custom_tokens={
            TokenType.IPV4: "<REDACTED_IP>",
            TokenType.PASSWORD: "<SECRET>",
        })
        assert mapper.get_token(TokenType.IPV4) == "<REDACTED_IP>"
        assert mapper.get_token(TokenType.PASSWORD) == "<SECRET>"

    def test_string_token_type(self):
        mapper = TokenMapper()
        assert mapper.get_token("ipv4") == "<ip_address>"
        assert mapper.get_token("password") == "<password>"


class TestRedactionLogger:
    def test_log_redaction(self):
        logger = RedactionLogger("test-org")
        entry = logger.log(
            original="secret123",
            replacement="<password>",
            line=10,
            data_type="password",
            tier=2,
        )
        assert entry.token == "<password>"
        assert entry.tier == 2
        assert len(entry.original_hash) == HASH_TRUNCATION

    def test_get_redaction_map(self):
        logger = RedactionLogger("test-org")
        logger.log("secret1", "<token>", 1, "password", 1)
        logger.log("10.0.0.1", "<ip>", 2, "ipv4", 2)

        redacted = logger.get_redaction_map()
        assert redacted["org_id"] == "test-org"
        assert redacted["tier_used"] == 1
        assert len(redacted["replacements"]) == 2

    def test_set_tiers_used(self):
        logger = RedactionLogger("test-org")
        logger.set_tiers_used([1, 2, 3])
        assert logger._tier_used == 1


class TestTierResolver:
    def test_register_and_has_template(self):
        resolver = TierResolver()
        assert not resolver.has_template("cisco_ios")

        resolver.register_template("cisco_ios")
        assert resolver.has_template("cisco_ios")

    def test_resolve_tier1_with_template(self):
        resolver = TierResolver()
        resolver.register_template("cisco_ios")

        tier = resolver.resolve("some config", "cisco_ios")
        assert tier == Tier.TIER_1

    def test_resolve_tier2_with_structure(self):
        resolver = TierResolver()
        config = """
hostname router-01
interface GigabitEthernet0/0
 ip address 10.0.0.1 255.255.255.0
"""
        tier = resolver.resolve(config, "unknown")
        assert tier == Tier.TIER_2

    def test_resolve_tier3_no_structure(self):
        resolver = TierResolver()
        tier = resolver.resolve("some random text without structure", "unknown")
        assert tier == Tier.TIER_3


class TestSectionRegexSanitizer:
    def test_detect_interface_section(self):
        sanitizer = SectionRegexSanitizer()
        config = """
interface GigabitEthernet0/0
 ip address 10.1.1.1 255.255.255.0
"""
        result = sanitizer.sanitize(config)
        assert "<ip_address>" in result.sanitized_text

    def test_detect_bgp_section(self):
        sanitizer = SectionRegexSanitizer()
        config = """
router bgp 65001
 neighbor 10.0.0.1 remote-as 65002
"""
        result = sanitizer.sanitize(config)
        assert "<ip_address>" in result.sanitized_text
        assert "<as_number>" in result.sanitized_text

    def test_detect_username_section(self):
        sanitizer = SectionRegexSanitizer()
        config = """
username admin password Cisc0123
username operator secret SuperSecret456
"""
        result = sanitizer.sanitize(config)
        assert "<password>" in result.sanitized_text
        assert "<secret>" in result.sanitized_text


class TestAggressiveRegexSanitizer:
    def test_ipv4_redaction(self):
        sanitizer = AggressiveRegexSanitizer()
        config = "ip address 192.168.1.1 255.255.255.0"
        result = sanitizer.sanitize(config)
        assert "192.168.1.1" not in result.sanitized_text
        assert "<ip_address>" in result.sanitized_text

    def test_ipv6_redaction(self):
        sanitizer = AggressiveRegexSanitizer()
        config = "ipv6 address 2001:0db8:85a3:0000:0000:8a2e:0370:7334"
        result = sanitizer.sanitize(config)
        assert "2001:0db8" not in result.sanitized_text

    def test_password_redaction(self):
        sanitizer = AggressiveRegexSanitizer()
        config = "password MySecretPass123"
        result = sanitizer.sanitize(config)
        assert "MySecretPass123" not in result.sanitized_text
        assert "<password>" in result.sanitized_text

    def test_mac_address_redaction(self):
        sanitizer = AggressiveRegexSanitizer()
        config = "switchport trunk allowed vlan 1-100"
        result = sanitizer.sanitize(config)
        assert "<vlan_id>" in result.sanitized_text

    def test_multiple_redactions_same_line(self):
        sanitizer = AggressiveRegexSanitizer()
        config = """
interface GigabitEthernet0/0
 ip address 10.1.1.1 255.255.255.0
 password MyPass123
"""
        result = sanitizer.sanitize(config)
        assert "10.1.1.1" not in result.sanitized_text
        assert "MyPass123" not in result.sanitized_text
        assert len(result.redactions) >= 2
