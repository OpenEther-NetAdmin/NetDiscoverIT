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
