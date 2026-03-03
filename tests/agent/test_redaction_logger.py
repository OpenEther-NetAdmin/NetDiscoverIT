import pytest
from agent.sanitizer.redaction_logger import RedactionLogger, RedactionEntry


def test_log_single_redaction():
    logger = RedactionLogger(org_id="test-org")
    entry = logger.log(
        original="10.1.1.1",
        replacement="<ip_address>",
        line=15,
        data_type="ipv4",
        tier=1
    )
    
    assert entry.line == 15
    assert entry.data_type == "ipv4"
    assert entry.token == "<ip_address>"
    assert entry.original_hash is not None  # SHA-256 hash


def test_get_redaction_map():
    logger = RedactionLogger(org_id="test-org")
    logger.log("10.1.1.1", "<ip_address>", 15, "ipv4", 1)
    logger.log("Cisco123", "<password>", 23, "password", 1)
    
    result = logger.get_redaction_map()
    assert result["org_id"] == "test-org"
    assert len(result["replacements"]) == 2
    assert result["tier_used"] == 1


def test_redaction_map_includes_timestamp():
    logger = RedactionLogger(org_id="test-org")
    logger.log("10.1.1.1", "<ip_address>", 1, "ipv4", 1)
    
    result = logger.get_redaction_map()
    assert "sanitized_at" in result
