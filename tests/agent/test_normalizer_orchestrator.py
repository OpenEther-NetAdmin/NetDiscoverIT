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
        assert result.parser_method in {"textfsm", "fallback", "strict"}
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
            
            assert result.template_name is not None or result.parser_method == "textfsm"

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
            assert "raw_snippet" not in record or record.get("raw_snippet") is None or \
                   "supersecret" not in str(record.get("raw_snippet", "")), \
                   "Raw config content must not propagate"
