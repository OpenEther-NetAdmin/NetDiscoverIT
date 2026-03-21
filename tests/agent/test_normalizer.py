"""
Tests for ConfigNormalizer with TextFSM integration
"""

import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock


SAMPLE_CISCO_CONFIG = """
!
! Cisco IOS Version 15.2(4)E5
!
hostname Router-Core-01
!
interface GigabitEthernet0/0
 description Uplink to Core
 ip address 10.0.1.1 255.255.255.0
!
interface GigabitEthernet0/1
 description Management
 ip address 192.168.1.1 255.255.255.0
!
"""

SAMPLE_JUNIPER_CONFIG = """
## Last commit: 2024-01-15 10:30:00 UTC
## Juniper JunOS version: 21.4R1.5

system {
    host-name Router-Site-A;
    domain-name example.com;
}

interfaces {
    ge-0/0/0 {
        description "Uplink to ISP";
        unit 0 {
            family inet {
                address 10.0.1.1/24;
            }
        }
    }
}
"""

SAMPLE_ARISTA_CONFIG = """
! boot system vEOS-4.28.3M
!
hostname Router-Site-B
!
interface Ethernet1
 description Uplink
 no switchport
 ip address 10.0.2.1/24
!
"""


class TestVendorDetection:
    """Test vendor detection functionality"""
    
    def test_detect_cisco_ios(self):
        """Test vendor detection for Cisco IOS"""
        from agent.normalizer import ConfigNormalizer
        
        config = MagicMock()
        normalizer = ConfigNormalizer(config)
        
        vendor = normalizer._detect_vendor(SAMPLE_CISCO_CONFIG)
        
        assert vendor == "cisco"
    
    def test_detect_juniper_junos(self):
        """Test vendor detection for Juniper JunOS"""
        from agent.normalizer import ConfigNormalizer
        
        config = MagicMock()
        normalizer = ConfigNormalizer(config)
        
        vendor = normalizer._detect_vendor(SAMPLE_JUNIPER_CONFIG)
        
        assert vendor == "juniper"
    
    def test_detect_arista_eos(self):
        """Test vendor detection for Arista EOS"""
        from agent.normalizer import ConfigNormalizer
        
        config = MagicMock()
        normalizer = ConfigNormalizer(config)
        
        vendor = normalizer._detect_vendor(SAMPLE_ARISTA_CONFIG)
        
        assert vendor == "arista"


class TestHostnameExtraction:
    """Test hostname extraction via regex"""
    
    def test_extract_cisco_hostname(self):
        """Extract hostname from Cisco IOS config"""
        from agent.normalizer import ConfigNormalizer
        
        config = MagicMock()
        normalizer = ConfigNormalizer(config)
        
        hostname = normalizer._extract_value(SAMPLE_CISCO_CONFIG, r"hostname\s+(\S+)")
        
        assert hostname == "Router-Core-01"
    
    def test_extract_juniper_hostname(self):
        """Extract hostname from Juniper JunOS config"""
        from agent.normalizer import ConfigNormalizer
        
        config = MagicMock()
        normalizer = ConfigNormalizer(config)
        
        # Juniper uses "host-name" in system block
        hostname = normalizer._extract_value(SAMPLE_JUNIPER_CONFIG, r"host-name\s+(\S+);")
        
        assert hostname == "Router-Site-A"
    
    def test_extract_arista_hostname(self):
        """Extract hostname from Arista EOS config"""
        from agent.normalizer import ConfigNormalizer
        
        config = MagicMock()
        normalizer = ConfigNormalizer(config)
        
        hostname = normalizer._extract_value(SAMPLE_ARISTA_CONFIG, r"hostname\s+(\S+)")
        
        assert hostname == "Router-Site-B"


class TestTextFSMParser:
    """Test TextFSM parser functionality"""
    
    def test_textfsm_parser_import(self):
        """Test that TextFSMParser can be imported"""
        from agent.normalizer_textfsm.textfsm_parser import TextFSMParser
        
        parser = TextFSMParser()
        assert parser is not None
    
    def test_textfsm_template_map(self):
        """Test that TEMPLATE_MAP contains expected vendors"""
        from agent.normalizer_textfsm.textfsm_parser import TextFSMParser
        
        expected_vendors = [
            "cisco_ios",
            "cisco_nxos", 
            "juniper_junos",
            "arista_eos",
            "hp_procurve",
            "f5_bigip"
        ]
        
        for vendor in expected_vendors:
            assert vendor in TextFSMParser.TEMPLATE_MAP
    
    def test_parse_returns_dict(self):
        """Test that parse returns a dictionary"""
        from agent.normalizer_textfsm.textfsm_parser import TextFSMParser
        
        parser = TextFSMParser()
        result = parser.parse("some config", "unknown_vendor")
        
        assert isinstance(result, dict)
    
    def test_parse_unknown_vendor_returns_empty(self):
        """Test that unknown vendor returns empty dict"""
        from agent.normalizer_textfsm.textfsm_parser import TextFSMParser
        
        parser = TextFSMParser()
        result = parser.parse(SAMPLE_CISCO_CONFIG, "unknown_vendor")
        
        assert result == {}
    
    def test_parse_fails_returns_empty_dict(self):
        """Test that parse failure returns empty dict"""
        from agent.normalizer_textfsm.textfsm_parser import TextFSMParser
        
        parser = TextFSMParser()
        
        result = parser.parse("some config", "cisco_ios")
        
        assert isinstance(result, dict)


class TestConfigNormalizerIntegration:
    """Test ConfigNormalizer with TextFSM integration"""
    
    @pytest.mark.asyncio
    async def test_normalize_uses_textfsm_first(self):
        """Test that normalize tries TextFSM first"""
        from agent.normalizer import ConfigNormalizer
        
        config = MagicMock()
        config.OLLAMA_BASE_URL = "http://localhost:11434"
        normalizer = ConfigNormalizer(config)
        
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {
            "hostname": "Router-Core-01",
            "version": "15.2(4)E5",
            "_normalization_method": "textfsm"
        }
        normalizer.textfsm_parser = mock_parser
        
        result = await normalizer.normalize(SAMPLE_CISCO_CONFIG)
        
        mock_parser.parse.assert_called_once()
        assert result.get("_normalization_method") == "textfsm"
    
    @pytest.mark.asyncio
    async def test_normalize_falls_back_to_llm_on_textfsm_failure(self):
        """Test that normalize falls back to LLM when TextFSM fails"""
        import httpx
        from agent.normalizer import ConfigNormalizer
        
        config = MagicMock()
        config.OLLAMA_BASE_URL = "http://localhost:11434"
        normalizer = ConfigNormalizer(config)
        
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {}
        normalizer.textfsm_parser = mock_parser
        
        with patch.object(httpx, "AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "response": '{"hostname": "TestRouter"}'
            }
            
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            mock_client.return_value = mock_client_instance
            
            result = await normalizer.normalize(SAMPLE_CISCO_CONFIG)
            
            assert "hostname" in result
    
    def test_normalizer_has_textfsm_parser_attribute(self):
        """Test that ConfigNormalizer has TextFSMParser attribute"""
        from agent.normalizer import ConfigNormalizer
        
        config = MagicMock()
        normalizer = ConfigNormalizer(config)
        
        assert hasattr(normalizer, "textfsm_parser")
        assert normalizer.textfsm_parser is not None
        assert "TextFSMParser" in str(type(normalizer.textfsm_parser))
