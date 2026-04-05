"""
Tests for normalization orchestrator entry point
"""

import pytest
from unittest.mock import MagicMock, patch


class TestNormalizeCommandOutput:
    """Test normalize_command_output entry point"""

    def test_normalize_command_output_returns_normalized_payload(self):
        """Test that normalize_command_output returns NormalizedCommandOutput"""
        from agent.normalizer import normalize_command_output
        
        result = normalize_command_output(
            vendor="cisco_ios",
            command="show version",
            raw_output="Cisco IOS Software, Version 15.2(4)E5\nhostname Router-01"
        )
        
        from services.common.normalization.schemas import NormalizedCommandOutput
        assert isinstance(result, NormalizedCommandOutput)

    def test_normalize_command_output_has_required_fields(self):
        """Test that result has required fields"""
        from agent.normalizer import normalize_command_output
        
        result = normalize_command_output(
            vendor="cisco_ios",
            command="show version",
            raw_output="Cisco IOS Software, Version 15.2(4)E5\nhostname Router-01"
        )
        
        assert result.vendor == "cisco_ios"
        assert result.command == "show version"
        assert result.parser_method in {"textfsm", "fallback"}
        assert result.schema_version == "1.0"

    def test_normalize_command_output_returns_textfsm_on_success(self):
        """Test that parser_method is textfsm when TextFSM succeeds"""
        from agent.normalizer import normalize_command_output
        from agent.normalizer_textfsm.textfsm_parser import TextFSMParser
        
        with patch.object(TextFSMParser, 'parse') as mock_parse:
            mock_parse.return_value = {
                "hostname": "Router-01",
                "version": "15.2(4)E5",
                "_normalization_method": "textfsm"
            }
            
            result = normalize_command_output(
                vendor="cisco_ios",
                command="show version",
                raw_output="Cisco IOS Software"
            )
            
            assert result.parser_method == "textfsm"
            assert result.parser_status == "success"

    def test_normalize_command_output_falls_back_on_textfsm_failure(self):
        """Test that fallback is used when TextFSM fails"""
        from agent.normalizer import normalize_command_output
        from agent.normalizer_textfsm.textfsm_parser import TextFSMParser
        
        with patch.object(TextFSMParser, 'parse') as mock_parse:
            mock_parse.return_value = {}
            
            result = normalize_command_output(
                vendor="cisco_ios",
                command="show version",
                raw_output="Some config"
            )
            
            assert result.parser_method == "fallback"
            assert result.parser_status == "fallback"

    def test_normalize_command_output_includes_records(self):
        """Test that parsed records are included in output"""
        from agent.normalizer import normalize_command_output
        from agent.normalizer_textfsm.textfsm_parser import TextFSMParser
        
        with patch.object(TextFSMParser, 'parse') as mock_parse:
            mock_parse.return_value = {
                "hostname": "Router-01",
                "version": "15.2(4)E5",
                "_normalization_method": "textfsm"
            }
            
            result = normalize_command_output(
                vendor="cisco_ios",
                command="show version",
                raw_output="Cisco IOS Software"
            )
            
            assert isinstance(result.records, list)
            assert len(result.records) > 0

    def test_normalize_command_output_unknown_vendor_uses_fallback(self):
        """Test that unknown vendor uses fallback parsing"""
        from agent.normalizer import normalize_command_output
        
        result = normalize_command_output(
            vendor="unknown_vendor",
            command="show version",
            raw_output="Some device config"
        )
        
        assert result.parser_method == "fallback"
        assert result.fallback_reason is not None

    def test_normalize_command_output_preserves_template_info(self):
        """Test that template info is preserved when available"""
        from agent.normalizer import normalize_command_output
        from agent.normalizer_textfsm.textfsm_parser import TextFSMParser
        
        with patch.object(TextFSMParser, 'parse') as mock_parse:
            mock_parse.return_value = {
                "hostname": "Router-01",
                "_normalization_method": "textfsm",
                "_template_name": "cisco_ios_show_version.textfsm"
            }
            
            result = normalize_command_output(
                vendor="cisco_ios",
                command="show version",
                raw_output="Cisco IOS Software"
            )
            
            assert result.template_name == "cisco_ios_show_version.textfsm"
            assert result.parser_method == "textfsm"

    def test_fallback_result_contains_no_raw_config(self):
        """Raw config text must never appear in normalized output"""
        from agent.normalizer import normalize_command_output

        result = normalize_command_output(
            vendor="unknown_vendor_xyz",
            command="show running-config",
            raw_output="hostname SecretRouter\npassword supersecret123\nsnmp-server community public RO"
        )
        for record in result.records:
            assert "raw_config" not in record, "raw_config key must not appear in normalized output"
            assert "raw_snippet" not in record, "raw_snippet key must not appear in normalized output"


def test_normalize_command_output_reuses_parser_instance():
    """normalize_command_output must reuse the module-level TextFSMParser, not create a new one."""
    from agent import normalizer as norm_module
    from agent.normalizer_textfsm.textfsm_parser import TextFSMParser

    init_call_count = []
    original_init = TextFSMParser.__init__

    def counting_init(self, *args, **kwargs):
        init_call_count.append(1)
        original_init(self, *args, **kwargs)

    with patch.object(TextFSMParser, "__init__", counting_init):
        norm_module._TEXTFSM_PARSER = None
        norm_module.normalize_command_output(
            vendor="cisco_ios", command="show version", raw_output="test"
        )
        norm_module.normalize_command_output(
            vendor="cisco_ios", command="show version", raw_output="test"
        )

    assert len(init_call_count) <= 1, (
        f"TextFSMParser.__init__ called {len(init_call_count)} times — "
        "should be created once and reused"
    )
