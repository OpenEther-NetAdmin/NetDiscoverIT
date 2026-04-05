"""
Config Normalizer
Converts vendor-specific configs to JSON using TextFSM or LLM
"""

import json
import logging
import os
from typing import Dict

from agent.normalizer_textfsm.textfsm_parser import TextFSMParser
from agent.sanitizer import ConfigSanitizer
from services.common.normalization.schemas import NormalizedCommandOutput

logger = logging.getLogger(__name__)

_TEXTFSM_PARSER: "TextFSMParser | None" = None


def _get_parser() -> "TextFSMParser":
    global _TEXTFSM_PARSER
    if _TEXTFSM_PARSER is None:
        _TEXTFSM_PARSER = TextFSMParser()
    return _TEXTFSM_PARSER


class ConfigNormalizer:
    """Normalizes vendor configs to JSON"""

    def __init__(self, config):
        self.config = config
        self.textfsm_parser = TextFSMParser()
        self._sanitizer = ConfigSanitizer(org_id=getattr(config, 'ORG_ID', 'default'))

    def _sanitize_for_cloud(self, raw_config: str) -> str:
        """Sanitize config for transmission to external cloud LLMs.
        
        Privacy architecture: When cloud LLM API keys are set, raw configs
        must be sanitized before sending to external APIs to prevent sensitive
        data from leaving the customer network.
        """
        result = self._sanitizer.sanitize(raw_config)
        if isinstance(result, dict):
            return result.get("sanitized", result.get("sanitized_config", raw_config))
        return result
    
    async def normalize(self, raw_config: str) -> Dict:
        """Convert raw config to JSON using TextFSM or LLM"""

        vendor = self._detect_vendor(raw_config)
        vendor_key = self._get_vendor_key(vendor)

        if vendor_key:
            try:
                textfsm_result = self.textfsm_parser.parse(raw_config, vendor_key)
                if textfsm_result and textfsm_result.get("_normalization_method") == "textfsm":
                    logger.info(f"Successfully normalized using TextFSM for vendor: {vendor}")
                    return textfsm_result
            except Exception as e:
                logger.warning(f"TextFSM normalization failed for {vendor}: {e}")

        try:
            return await self._normalize_ollama(raw_config)
        except Exception as e:
            logger.warning(f"Ollama normalization failed: {e}")

        try:
            return await self._normalize_gemini(raw_config)
        except Exception as e:
            logger.warning(f"Gemini normalization failed: {e}")

        try:
            return await self._normalize_anthropic(raw_config)
        except Exception as e:
            logger.warning(f"Anthropic normalization failed: {e}")

        return self._normalize_rulebased(raw_config)

    def _get_vendor_key(self, vendor: str) -> str:
        """Map detected vendor to TextFSM template key"""
        vendor_map = {
            "cisco": "cisco_ios",
            "juniper": "juniper_junos",
            "arista": "arista_eos",
            "f5": "f5_bigip",
            "hp": "hp_procurve",
        }
        return vendor_map.get(vendor.lower(), "")
    
    async def _normalize_ollama(self, raw_config: str) -> Dict:
        """Use Ollama for normalization"""
        import httpx
        
        base_url = getattr(self.config, 'OLLAMA_BASE_URL', 'http://localhost:11434')
        model = getattr(self.config, 'OLLAMA_MODEL', 'llama3.2:7b')
        
        prompt = f"""Convert this network device configuration to JSON.
Only include factual information from the config. Do not infer or add fields.

Configuration:
{raw_config}

Output valid JSON only, no explanations:"""
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"
                },
                timeout=60.0
            )
            
            if response.status_code == 200:
                result = response.json()
                text = result.get('response', '')
                return json.loads(text)
            else:
                raise Exception(f"Ollama error: {response.status_code}")
    
    async def _normalize_gemini(self, raw_config: str) -> Dict:
        """Use Google Gemini for normalization"""
        import httpx
        
        api_key = getattr(self.config, 'GOOGLE_API_KEY', None) or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise Exception("GOOGLE_API_KEY not set")
        
        sanitized_config = self._sanitize_for_cloud(raw_config)
        
        prompt = f"""Convert this network device configuration to JSON.
Only include factual information from the config. Do not infer or add fields.

Configuration:
{sanitized_config[:8000]}  # Limit length

Output valid JSON only, no explanations. Start your response with {{
"""

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-pro:generateContent",
                params={"key": api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 4000,
                        "responseMimeType": "application/json"
                    }
                },
                timeout=60.0
            )
            
            if response.status_code == 200:
                result = response.json()
                text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                return json.loads(text)
            else:
                raise Exception(f"Gemini error: {response.status_code} - {response.text}")
    
    async def _normalize_anthropic(self, raw_config: str) -> Dict:
        """Use Anthropic Claude for normalization"""
        from anthropic import Anthropic
        
        api_key = getattr(self.config, 'ANTHROPIC_API_KEY', None) or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise Exception("ANTHROPIC_API_KEY not set")
        
        model = getattr(self.config, 'ANTHROPIC_MODEL', 'claude-sonnet-4-20250514')
        
        client = Anthropic(api_key=api_key)
        
        sanitized_config = self._sanitize_for_cloud(raw_config)
        
        prompt = f"""Convert this network device configuration to JSON.
Only include factual information from the config. Do not infer or add fields.

Configuration:
{sanitized_config[:10000]}  # Limit length

Output valid JSON only, no explanations:"""
        
        message = client.messages.create(
            model=model,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return json.loads(message.content[0].text)
    
    def _normalize_rulebased(self, raw_config: str) -> Dict:
        """Fallback rule-based normalization — extracts structured facts only.

        PRIVACY: raw config text is never included in output. Only parsed
        structural facts (hostname, vendor, interfaces, VLANs) are returned.
        """
        result = {
            "hostname": self._extract_value(raw_config, r"hostname\s+(\S+)"),
            "vendor": self._detect_vendor(raw_config),
            "interfaces": self._extract_interfaces(raw_config),
            "vlans": self._extract_vlans(raw_config),
            "_parse_quality": "rule_based_only",
        }

        return result
    
    def _extract_value(self, config: str, pattern: str) -> str:
        """Extract value using regex"""
        import re
        match = re.search(pattern, config, re.IGNORECASE)
        return match.group(1) if match else ""
    
    def _detect_vendor(self, config: str) -> str:
        """Detect vendor from config"""
        config_lower = config.lower()
        
        if "cisco" in config_lower or "ios" in config_lower:
            return "cisco"
        elif "juniper" in config_lower or "junos" in config_lower:
            return "juniper"
        elif "arista" in config_lower or "eos" in config_lower:
            return "arista"
        elif "f5" in config_lower:
            return "f5"
        elif "palo alto" in config_lower:
            return "palo_alto"
        
        return "unknown"
    
    def _extract_interfaces(self, config: str) -> list:
        """Extract interfaces from config"""
        import re
        
        interfaces = []
        
        # Match interface blocks
        pattern = r"interface\s+(\S+.*?)(?=^interface|\Z)"
        matches = re.finditer(pattern, config, re.MULTILINE | re.DOTALL)
        
        for match in matches:
            iface_lines = match.group(1).strip().split('\n')
            iface_name = iface_lines[0].strip()
            
            iface = {"name": iface_name}
            
            # Extract IP if present
            ip_match = re.search(r"ip address\s+(\S+)\s+(\S+)", iface_lines[0])
            if ip_match:
                iface["ip_address"] = ip_match.group(1)
                iface["subnet"] = ip_match.group(2)
            
            # Extract description
            desc_match = re.search(r"description\s+(.+)", '\n'.join(iface_lines))
            if desc_match:
                iface["description"] = desc_match.group(1).strip()
            
            # Extract VLAN
            vlan_match = re.search(r"switchport access vlan\s+(\d+)", '\n'.join(iface_lines))
            if vlan_match:
                iface["access_vlan"] = int(vlan_match.group(1))
            
            interfaces.append(iface)
        
        return interfaces
    
    def _extract_vlans(self, config: str) -> list:
        """Extract VLANs from config"""
        import re
        
        vlans = []
        
        # Match VLAN definitions
        pattern = r"vlan\s+(\d+)"
        matches = re.finditer(pattern, config)
        
        for match in matches:
            vlan_id = int(match.group(1))
            
            # Try to find name
            name_match = re.search(rf"vlan\s+{vlan_id}.*?name\s+(\S+)", config, re.IGNORECASE)
            name = name_match.group(1) if name_match else f"VLAN{vlan_id}"
            
            vlans.append({"id": vlan_id, "name": name})
        
        return vlans


def normalize_command_output(
    vendor: str,
    command: str,
    raw_output: str,
    strict: bool = False
) -> NormalizedCommandOutput:
    """Orchestrate normalization of command output.
    
    Entry point that routes through TextFSM parser first, then falls back
    to rule-based parsing if no template is available.
    
    Args:
        vendor: Vendor key (e.g., "cisco_ios", "juniper_junos")
        command: Command that was executed (e.g., "show version")
        raw_output: Raw command output text
        strict: If True, fail on parse errors instead of falling back
        
    Returns:
        NormalizedCommandOutput with parsed records and metadata
    """
    parser = _get_parser()
    
    result = NormalizedCommandOutput(
        vendor=vendor,
        command=command,
        records=[],
        parser_method="fallback",
        parser_status="fallback",
        fallback_reason="No template available"
    )
    
    try:
        parsed = parser.parse(raw_output, vendor)
        
        if parsed and parsed.get("_normalization_method") == "textfsm":
            records = [{k: v for k, v in parsed.items() if not k.startswith("_")}]
            
            result.records = records
            result.parser_method = "textfsm"
            result.parser_status = "success"
            result.fallback_reason = None
            result.template_name = parsed.get("_template_name")
            
            return result
    except Exception as e:
        logger.warning(f"TextFSM parsing failed for {vendor}/{command}: {e}")
        if strict:
            result.parser_status = "error"
            result.warnings.append(str(e))
            return result
    
    fallback_records = _fallback_parse(raw_output, vendor)
    result.records = fallback_records
    result.parser_method = "fallback"
    result.parser_status = "fallback"
    result.fallback_reason = "TextFSM template not available or parsing failed"
    
    return result


def _fallback_parse(raw_output: str, vendor: str) -> list:
    """Simple fallback parser when TextFSM is unavailable.

    PRIVACY: raw output is never stored. Only extracted structured facts.
    """
    import re

    records = []
    record = {}

    hostname_match = re.search(r"hostname\s+(\S+)", raw_output, re.IGNORECASE)
    if hostname_match:
        record["hostname"] = hostname_match.group(1)

    version_match = re.search(r"version\s+([\d\.\(\)]+)", raw_output, re.IGNORECASE)
    if version_match:
        record["version"] = version_match.group(1)

    record["vendor"] = vendor
    record["_parse_quality"] = "regex_fallback"
    records.append(record)

    return records
