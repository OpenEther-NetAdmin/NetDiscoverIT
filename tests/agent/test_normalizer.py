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


class TestCloudLLMPrivacy:
    """Test that cloud LLM methods send sanitized config, not raw config"""
    
    SAMPLE_CONFIG_WITH_SECRETS = """
hostname Router-Critical-01
!
interface GigabitEthernet0/0
 description Uplink to Core
 ip address 10.0.1.1 255.255.255.0
!
enable password SuperSecret123
username admin password AdminPass456
snmp-server community public
!
"""
    
    @pytest.mark.asyncio
    async def test_gemini_sends_sanitized_config(self):
        """Test that Gemini normalization sends sanitized config when GOOGLE_API_KEY is set"""
        import httpx
        from agent.normalizer import ConfigNormalizer
        
        config = MagicMock()
        config.OLLAMA_BASE_URL = "http://localhost:11434"
        normalizer = ConfigNormalizer(config)
        
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {}
        normalizer.textfsm_parser = mock_parser
        
        with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test-key'}):
            with patch.object(httpx, 'AsyncClient') as mock_client:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    'candidates': [{
                        'content': {
                            'parts': [{'text': '{"hostname": "Router"}'}]
                        }
                    }]
                }
                
                mock_client_instance = AsyncMock()
                mock_client_instance.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
                mock_client.return_value = mock_client_instance
                
                await normalizer.normalize(self.SAMPLE_CONFIG_WITH_SECRETS)
                
                call_args = mock_client_instance.__aenter__.return_value.post.call_args
                prompt_text = call_args.kwargs['json']['contents'][0]['parts'][0]['text']
                
                assert 'SuperSecret123' not in prompt_text, "Raw secret password should not be in prompt"
                assert 'AdminPass456' not in prompt_text, "Raw admin password should not be in prompt"
                assert 'public' not in prompt_text or '<community_string>' in prompt_text, "SNMP community should be sanitized"
    
    @pytest.mark.asyncio
    async def test_anthropic_sends_sanitized_config(self):
        """Test that Anthropic normalization sends sanitized config when ANTHROPIC_API_KEY is set"""
        from agent.normalizer import ConfigNormalizer
        
        config = MagicMock()
        config.OLLAMA_BASE_URL = "http://localhost:11434"
        normalizer = ConfigNormalizer(config)
        
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {}
        normalizer.textfsm_parser = mock_parser
        
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
            with patch('anthropic.Anthropic') as mock_anthropic_class:
                mock_instance = MagicMock()
                mock_message = MagicMock()
                mock_message.content = [MagicMock(text='{"hostname": "Router"}')]
                mock_instance.messages.create.return_value = mock_message
                mock_anthropic_class.return_value = mock_instance
                
                await normalizer.normalize(self.SAMPLE_CONFIG_WITH_SECRETS)
                
                mock_instance.messages.create.assert_called_once()
                call_kwargs = mock_instance.messages.create.call_args.kwargs
                prompt_text = call_kwargs['messages'][0]['content']
                
                assert 'SuperSecret123' not in prompt_text, "Raw secret password should not be in prompt"
                assert 'AdminPass456' not in prompt_text, "Raw admin password should not be in prompt"
                assert 'public' not in prompt_text or '<community_string>' in prompt_text, "SNMP community should be sanitized"
    
    def test_sanitize_for_cloud_removes_secrets(self):
        """Test that _sanitize_for_cloud removes sensitive data"""
        from agent.normalizer import ConfigNormalizer
        
        config = MagicMock()
        normalizer = ConfigNormalizer(config)
        
        raw_config = """
hostname TestRouter
enable password SuperSecret123
username admin password AdminPass456
snmp-server community public
"""
        sanitized = normalizer._sanitize_for_cloud(raw_config)
        
        assert 'SuperSecret123' not in sanitized, "Raw secret password should be removed"
        assert 'AdminPass456' not in sanitized, "Raw admin password should be removed"
        assert 'password' in sanitized.lower() and ('<password>' in sanitized or '***' in sanitized), \
            "Password pattern should be sanitized to token"
    
    def test_normalizer_has_sanitizer(self):
        """Test that ConfigNormalizer has a sanitizer instance"""
        from agent.normalizer import ConfigNormalizer
        
        config = MagicMock()
        normalizer = ConfigNormalizer(config)
        
        assert hasattr(normalizer, '_sanitizer')
        assert normalizer._sanitizer is not None
