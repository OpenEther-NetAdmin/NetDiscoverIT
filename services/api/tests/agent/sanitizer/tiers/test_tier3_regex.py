import pytest
from agent.sanitizer.tiers.tier3_regex import AggressiveRegexSanitizer


def test_sanitize_ipv4_addresses():
    sanitizer = AggressiveRegexSanitizer()
    config = "ip address 10.1.1.1 255.255.255.0"
    result = sanitizer.sanitize(config)

    assert "10.1.1.1" not in result.sanitized_text
    assert "<ip_address>" in result.sanitized_text


def test_sanitize_passwords():
    sanitizer = AggressiveRegexSanitizer()
    config = "username admin password Cisco123"
    result = sanitizer.sanitize(config)

    assert "Cisco123" not in result.sanitized_text
    assert "<password>" in result.sanitized_text


def test_sanitize_snmp_community():
    sanitizer = AggressiveRegexSanitizer()
    config = "snmp-server community public RO"
    result = sanitizer.sanitize(config)

    assert "public" not in result.sanitized_text
    assert "<community_string>" in result.sanitized_text


def test_redaction_map_tracks_replacements():
    sanitizer = AggressiveRegexSanitizer()
    config = "ip address 10.1.1.1 255.255.255.0\nusername admin secret Cisco123"
    result = sanitizer.sanitize(config)

    assert len(result.redactions) >= 2
    assert any(r["data_type"] == "ipv4" for r in result.redactions)
    assert any(r["data_type"] == "secret" for r in result.redactions)


def test_preserves_config_structure():
    sanitizer = AggressiveRegexSanitizer()
    config = "interface GigabitEthernet0/1\n ip address 10.1.1.1 255.255.255.0\n!"
    result = sanitizer.sanitize(config)

    assert "interface" in result.sanitized_text
    assert "GigabitEthernet0/1" in result.sanitized_text  # Interface names preserved
    assert "!" in result.sanitized_text


def test_sanitize_secret_without_encryption_level():
    """Test that secrets without encryption level are correctly captured (bug fix)."""
    sanitizer = AggressiveRegexSanitizer()
    config = "username admin secret Cisco123"
    result = sanitizer.sanitize(config)

    assert "Cisco123" not in result.sanitized_text
    assert "<secret>" in result.sanitized_text
    # Verify the redaction captured the actual secret, not None
    secret_redactions = [r for r in result.redactions if r["data_type"] == "secret"]
    assert len(secret_redactions) == 1
    assert secret_redactions[0]["original"] == "Cisco123"


def test_vlan_preserves_prefix():
    """Test that vlan keyword is preserved when replacing VLAN ID."""
    sanitizer = AggressiveRegexSanitizer()
    config = "vlan 100"
    result = sanitizer.sanitize(config)

    assert "100" not in result.sanitized_text
    assert "vlan <vlan_id>" in result.sanitized_text
    assert result.sanitized_text.strip() == "vlan <vlan_id>"


def test_password_preserves_prefix():
    """Test that password keyword is preserved when replacing password."""
    sanitizer = AggressiveRegexSanitizer()
    config = "username admin password Cisco123"
    result = sanitizer.sanitize(config)

    assert "Cisco123" not in result.sanitized_text
    assert "password <password>" in result.sanitized_text


def test_secret_with_encryption_level_preserves_prefix():
    """Test that secret keyword and encryption level are preserved."""
    sanitizer = AggressiveRegexSanitizer()
    config = "username admin secret 5 $1$abcd$1234"
    result = sanitizer.sanitize(config)

    assert "$1$abcd$1234" not in result.sanitized_text
    assert "secret 5 <secret>" in result.sanitized_text


def test_secret_without_encryption_level_preserves_prefix():
    """Test that secret keyword is preserved when no encryption level."""
    sanitizer = AggressiveRegexSanitizer()
    config = "username admin secret PlainSecret"
    result = sanitizer.sanitize(config)

    assert "PlainSecret" not in result.sanitized_text
    assert "secret <secret>" in result.sanitized_text


def test_snmp_server_community_preserves_prefix():
    """Test that snmp-server community keywords are preserved."""
    sanitizer = AggressiveRegexSanitizer()
    config = "snmp-server community public RO"
    result = sanitizer.sanitize(config)

    assert "public" not in result.sanitized_text
    assert "snmp-server community <community_string>" in result.sanitized_text


def test_router_bgp_preserves_prefix():
    """Test that router bgp keywords are preserved when replacing AS number."""
    sanitizer = AggressiveRegexSanitizer()
    config = "router bgp 65001"
    result = sanitizer.sanitize(config)

    assert "65001" not in result.sanitized_text
    assert "router bgp <as_number>" in result.sanitized_text


def test_ipv6_address_sanitized():
    """Test that IPv6 addresses are sanitized."""
    sanitizer = AggressiveRegexSanitizer()
    config = "ipv6 address 2001:0db8:85a3:0000:0000:8a2e:0370:7334/64"
    result = sanitizer.sanitize(config)

    assert "2001:0db8:85a3:0000:0000:8a2e:0370:7334" not in result.sanitized_text
    assert "<ipv6_address>" in result.sanitized_text


def test_config_structure_preserved_real_world():
    """Test that real-world config structure is preserved after sanitization."""
    sanitizer = AggressiveRegexSanitizer()
    config = """vlan 100
 name Management
!
interface Vlan100
 ip address 10.1.100.1 255.255.255.0
!
router bgp 65001
 neighbor 10.1.100.2 remote-as 65002
!
snmp-server community public RO
username admin password Cisco123
username admin secret 5 $1$abcd$1234"""
    result = sanitizer.sanitize(config)

    # Check prefixes are preserved
    assert "vlan <vlan_id>" in result.sanitized_text
    assert "router bgp <as_number>" in result.sanitized_text
    assert "snmp-server community <community_string>" in result.sanitized_text
    assert "password <password>" in result.sanitized_text
    assert "secret 5 <secret>" in result.sanitized_text

    # Check structure keywords preserved
    assert "name Management" in result.sanitized_text
    assert "interface Vlan100" in result.sanitized_text
    assert "neighbor" in result.sanitized_text
    assert "remote-as" in result.sanitized_text
