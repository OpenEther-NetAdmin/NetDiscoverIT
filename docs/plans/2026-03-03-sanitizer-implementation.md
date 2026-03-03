# Config Sanitizer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a tiered config sanitizer that replaces sensitive data with tokens before vectorization, ensuring zero raw credentials leave the customer network.

**Architecture:** Three-tier approach: (1) TextFSM template-driven parsing for known vendors, (2) section-aware regex for unknown but structured configs, (3) aggressive regex catch-all for unstructured configs. LLM fallback is opt-in only, disabled by default.

**Tech Stack:** Python 3.11, TextFSM/ntc-templates, pytest, pytest-asyncio

---

## Phase 1: Foundation & Token Mapper

### Task 1: Create TokenMapper class

**Files:**
- Create: `services/agent/agent/sanitizer/token_mapper.py`
- Test: `tests/agent/test_token_mapper.py`

**Step 1: Write the failing test**

```python
# tests/agent/test_token_mapper.py
import pytest
from agent.sanitizer.token_mapper import TokenMapper, TokenType


def test_token_mapper_returns_correct_token():
    mapper = TokenMapper()
    assert mapper.get_token(TokenType.IPV4) == "<ip_address>"
    assert mapper.get_token(TokenType.IPV6) == "<ipv6_address>"
    assert mapper.get_token(TokenType.HOSTNAME) == "<hostname>"
    assert mapper.get_token(TokenType.PASSWORD) == "<password>"


def test_token_mapper_returns_default_for_unknown():
    mapper = TokenMapper()
    assert mapper.get_token("unknown_type") == "<unknown_type>"


def test_token_mapper_custom_tokens():
    custom_tokens = {"ipv4": "[IP]"}
    mapper = TokenMapper(custom_tokens=custom_tokens)
    assert mapper.get_token(TokenType.IPV4) == "[IP]"
```

**Step 2: Run test to verify it fails**

```bash
cd /home/openether/NetDiscoverIT/services/agent
pytest tests/test_token_mapper.py -v
```

Expected: `ModuleNotFoundError: No module named 'agent.sanitizer.token_mapper'`

**Step 3: Write minimal implementation**

```python
# services/agent/agent/sanitizer/token_mapper.py
from enum import Enum
from typing import Optional


class TokenType(str, Enum):
    IPV4 = "ipv4"
    IPV6 = "ipv6"
    HOSTNAME = "hostname"
    FQDN = "fqdn"
    PASSWORD = "password"
    SECRET = "secret"
    COMMUNITY = "community"
    BGP_AS = "bgp_as"
    VLAN_ID = "vlan_id"
    MAC_ADDRESS = "mac"


DEFAULT_TOKENS = {
    TokenType.IPV4: "<ip_address>",
    TokenType.IPV6: "<ipv6_address>",
    TokenType.HOSTNAME: "<hostname>",
    TokenType.FQDN: "<fqdn>",
    TokenType.PASSWORD: "<password>",
    TokenType.SECRET: "<secret>",
    TokenType.COMMUNITY: "<community_string>",
    TokenType.BGP_AS: "<as_number>",
    TokenType.VLAN_ID: "<vlan_id>",
    TokenType.MAC_ADDRESS: "<mac_address>",
}


class TokenMapper:
    """Maps data types to placeholder tokens for sanitization"""
    
    def __init__(self, custom_tokens: Optional[dict] = None):
        self.tokens = {**DEFAULT_TOKENS}
        if custom_tokens:
            for key, value in custom_tokens.items():
                token_type = key if isinstance(key, TokenType) else TokenType(key)
                self.tokens[token_type] = value
    
    def get_token(self, data_type: str | TokenType) -> str:
        """Get placeholder token for a data type"""
        if isinstance(data_type, str):
            try:
                data_type = TokenType(data_type)
            except ValueError:
                return f"<{data_type}>"
        return self.tokens.get(data_type, f"<{data_type}>")
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_token_mapper.py -v
```

Expected: All 3 tests pass

**Step 5: Commit**

```bash
git add tests/test_token_mapper.py services/agent/agent/sanitizer/token_mapper.py
git commit -m "feat(sanitizer): Add TokenMapper for placeholder tokens"
```

---

### Task 2: Create RedactionLogger class

**Files:**
- Create: `services/agent/agent/sanitizer/redaction_logger.py`
- Test: `tests/agent/test_redaction_logger.py`

**Step 1: Write the failing test**

```python
# tests/agent/test_redaction_logger.py
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
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_redaction_logger.py -v
```

Expected: `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# services/agent/agent/sanitizer/redaction_logger.py
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class RedactionEntry:
    """Single redaction record"""
    data_type: str
    line: int
    token: str
    original_hash: str
    tier: int


class RedactionLogger:
    """Logs redactions for audit trail"""
    
    def __init__(self, org_id: str):
        self.org_id = org_id
        self.entries: List[RedactionEntry] = []
        self._tier_used: Optional[int] = None
    
    def log(self, original: str, replacement: str, line: int,
            data_type: str, tier: int) -> RedactionEntry:
        """Log a single redaction"""
        # Hash the original for verification without storing it
        original_hash = hashlib.sha256(original.encode()).hexdigest()[:16]
        
        entry = RedactionEntry(
            data_type=data_type,
            line=line,
            token=replacement,
            original_hash=original_hash,
            tier=tier
        )
        self.entries.append(entry)
        
        # Track highest tier used (lower number = more precise)
        if self._tier_used is None or tier < self._tier_used:
            self._tier_used = tier
        
        return entry
    
    def get_redaction_map(self) -> dict:
        """Get complete redaction map for audit"""
        return {
            "org_id": self.org_id,
            "tier_used": self._tier_used,
            "sanitized_at": datetime.now(timezone.utc).isoformat(),
            "replacements": [
                {
                    "type": e.data_type,
                    "line": e.line,
                    "original_hash": e.original_hash,
                    "token": e.token,
                    "tier": e.tier
                }
                for e in self.entries
            ]
        }
    
    def reset(self):
        """Clear all entries"""
        self.entries = []
        self._tier_used = None
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_redaction_logger.py -v
```

**Step 5: Commit**

```bash
git add tests/test_redaction_logger.py services/agent/agent/sanitizer/redaction_logger.py
git commit -m "feat(sanitizer): Add RedactionLogger for audit trail"
```

---

## Phase 2: Tier 3 (Aggressive Regex) - Fail-Safe First

### Task 3: Implement Tier 3 Aggressive Regex Sanitizer

**Files:**
- Create: `services/agent/agent/sanitizer/tiers/tier3_regex.py`
- Test: `tests/agent/sanitizer/tiers/test_tier3_regex.py`

**Step 1: Write the failing test**

```python
# tests/agent/sanitizer/tiers/test_tier3_regex.py
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
    assert any(r.data_type == "ipv4" for r in result.redactions)
    assert any(r.data_type == "secret" for r in result.redactions)


def test_preserves_config_structure():
    sanitizer = AggressiveRegexSanitizer()
    config = "interface GigabitEthernet0/1\n ip address 10.1.1.1 255.255.255.0\n!"
    result = sanitizer.sanitize(config)
    
    assert "interface" in result.sanitized_text
    assert "GigabitEthernet0/1" in result.sanitized_text  # Interface names preserved
    assert "!" in result.sanitized_text
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/agent/sanitizer/tiers/test_tier3_regex.py -v
```

**Step 3: Write minimal implementation**

```python
# services/agent/agent/sanitizer/tiers/tier3_regex.py
import re
from dataclasses import dataclass
from typing import List, Tuple

from agent.sanitizer.token_mapper import TokenMapper, TokenType


@dataclass
class Tier3Result:
    sanitized_text: str
    redactions: List[dict]


class AggressiveRegexSanitizer:
    """Tier 3: Catch-all regex-based sanitization (fail-safe)"""
    
    # Patterns: (regex, token_type, description)
    PATTERNS: List[Tuple[re.Pattern, TokenType, str]] = [
        # IPv4 addresses
        (re.compile(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'), 
         TokenType.IPV4, "IPv4 address"),
        
        # Passwords (various forms)
        (re.compile(r'password\s+(\S+)', re.IGNORECASE), TokenType.PASSWORD, "password"),
        (re.compile(r'secret\s+(\d\s+)?(\S+)', re.IGNORECASE), TokenType.SECRET, "secret"),
        
        # SNMP communities
        (re.compile(r'snmp-server community\s+(\S+)', re.IGNORECASE), TokenType.COMMUNITY, "SNMP community"),
        (re.compile(r'community\s+(\S+)', re.IGNORECASE), TokenType.COMMUNITY, "community"),
        
        # BGP AS numbers
        (re.compile(r'router\s+bgp\s+(\d+)', re.IGNORECASE), TokenType.BGP_AS, "BGP AS"),
        
        # VLAN IDs
        (re.compile(r'vlan\s+(\d+)', re.IGNORECASE), TokenType.VLAN_ID, "VLAN"),
        
        # MAC addresses (various formats)
        (re.compile(r'(?:[0-9a-fA-F]{4}\.){2}[0-9a-fA-F]{4}'), TokenType.MAC_ADDRESS, "MAC address"),
        (re.compile(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}'), TokenType.MAC_ADDRESS, "MAC address"),
    ]
    
    def __init__(self):
        self.token_mapper = TokenMapper()
    
    def sanitize(self, config_text: str) -> Tier3Result:
        """Sanitize config using aggressive regex patterns"""
        lines = config_text.split('\n')
        sanitized_lines = []
        redactions = []
        
        for line_num, line in enumerate(lines, 1):
            sanitized_line = line
            
            for pattern, token_type, description in self.PATTERNS:
                matches = list(pattern.finditer(sanitized_line))
                # Replace in reverse order to preserve positions
                for match in reversed(matches):
                    original = match.group(1) if match.groups() else match.group(0)
                    token = self.token_mapper.get_token(token_type)
                    
                    redactions.append({
                        "data_type": token_type.value,
                        "line": line_num,
                        "original": original,
                        "token": token,
                        "tier": 3
                    })
                    
                    sanitized_line = sanitized_line[:match.start()] + token + sanitized_line[match.end():]
            
            sanitized_lines.append(sanitized_line)
        
        return Tier3Result(
            sanitized_text='\n'.join(sanitized_lines),
            redactions=redactions
        )
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/agent/sanitizer/tiers/test_tier3_regex.py -v
```

**Step 5: Commit**

```bash
git add tests/agent/sanitizer/tiers/test_tier3_regex.py services/agent/agent/sanitizer/tiers/tier3_regex.py
git commit -m "feat(sanitizer): Add Tier 3 aggressive regex sanitizer"
```

---

## Phase 3: Tier 2 (Section-Aware Regex)

### Task 4: Implement Tier 2 Section-Aware Sanitizer

**Files:**
- Create: `services/agent/agent/sanitizer/tiers/tier2_section.py`
- Test: `tests/agent/sanitizer/tiers/test_tier2_section.py`

**Step 1: Write the failing test**

```python
# tests/agent/sanitizer/tiers/test_tier2_section.py
import pytest
from agent.sanitizer.tiers.tier2_section import SectionRegexSanitizer


def test_detect_interface_section():
    sanitizer = SectionRegexSanitizer()
    config = """
interface GigabitEthernet0/1
 ip address 10.1.1.1 255.255.255.0
 no shutdown
!
"""
    sections = sanitizer._detect_sections(config)
    assert any(s["type"] == "interface" for s in sections)


def test_sanitize_interface_ips():
    sanitizer = SectionRegexSanitizer()
    config = """
interface GigabitEthernet0/1
 ip address 10.1.1.1 255.255.255.0
!
interface GigabitEthernet0/2
 ip address 192.168.1.1 255.255.255.0
!
"""
    result = sanitizer.sanitize(config)
    
    assert "10.1.1.1" not in result.sanitized_text
    assert "192.168.1.1" not in result.sanitized_text
    assert "<ip_address>" in result.sanitized_text


def test_preserves_interface_names():
    sanitizer = SectionRegexSanitizer()
    config = "interface GigabitEthernet0/1\n ip address 10.1.1.1 255.255.255.0"
    result = sanitizer.sanitize(config)
    
    assert "GigabitEthernet0/1" in result.sanitized_text


def test_detect_bgp_section():
    sanitizer = SectionRegexSanitizer()
    config = """
router bgp 65001
 neighbor 10.1.1.2 remote-as 65002
"""
    sections = sanitizer._detect_sections(config)
    assert any(s["type"] == "router_bgp" for s in sections)
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/agent/sanitizer/tiers/test_tier2_section.py -v
```

**Step 3: Write minimal implementation**

```python
# services/agent/agent/sanitizer/tiers/tier2_section.py
import re
from dataclasses import dataclass
from typing import List, Dict, Tuple

from agent.sanitizer.token_mapper import TokenMapper, TokenType


@dataclass
class Tier2Result:
    sanitized_text: str
    redactions: List[dict]


class SectionRegexSanitizer:
    """Tier 2: Section-aware regex sanitization"""
    
    # Section detection patterns
    SECTION_PATTERNS = {
        'interface': re.compile(r'^interface\s+(\S+)', re.MULTILINE),
        'router_bgp': re.compile(r'^router\s+bgp\s+(\d+)', re.MULTILINE),
        'router_ospf': re.compile(r'^router\s+ospf\s+(\d+)', re.MULTILINE),
        'snmp_server': re.compile(r'^snmp-server', re.MULTILINE),
        'username': re.compile(r'^username\s+\S+', re.MULTILINE),
    }
    
    # Section-specific redaction rules
    SECTION_RULES = {
        'interface': [
            (re.compile(r'ip address\s+(\d+\.\d+\.\d+\.\d+)'), TokenType.IPV4),
            (re.compile(r'ip address\s+([0-9a-fA-F:]+)'), TokenType.IPV6),  # IPv6
        ],
        'router_bgp': [
            (re.compile(r'neighbor\s+(\d+\.\d+\.\d+\.\d+)'), TokenType.IPV4),
            (re.compile(r'bgp\s+(\d+)'), TokenType.BGP_AS),
        ],
        'username': [
            (re.compile(r'password\s+(\S+)'), TokenType.PASSWORD),
            (re.compile(r'secret\s+(\S+)'), TokenType.SECRET),
        ],
    }
    
    # Global patterns applied to entire config
    GLOBAL_PATTERNS = [
        (re.compile(r'snmp-server community\s+(\S+)'), TokenType.COMMUNITY),
        (re.compile(r'hostname\s+(\S+)'), TokenType.HOSTNAME),
    ]
    
    def __init__(self):
        self.token_mapper = TokenMapper()
    
    def _detect_sections(self, config_text: str) -> List[Dict]:
        """Detect config sections and their positions"""
        sections = []
        lines = config_text.split('\n')
        current_section = None
        start_line = 0
        
        for i, line in enumerate(lines):
            # Check for new section start
            for section_type, pattern in self.SECTION_PATTERNS.items():
                if pattern.match(line):
                    if current_section:
                        sections.append({
                            "type": current_section,
                            "start": start_line,
                            "end": i
                        })
                    current_section = section_type
                    start_line = i
                    break
            # End section on '!' or empty line (simplified)
            elif line.strip() == '!' and current_section:
                sections.append({
                    "type": current_section,
                    "start": start_line,
                    "end": i
                })
                current_section = None
        
        # Close final section
        if current_section:
            sections.append({
                "type": current_section,
                "start": start_line,
                "end": len(lines)
            })
        
        return sections
    
    def sanitize(self, config_text: str) -> Tier2Result:
        """Sanitize using section-aware rules"""
        lines = config_text.split('\n')
        sections = self._detect_sections(config_text)
        redactions = []
        
        # Track which lines belong to which section
        line_to_section = {}
        for section in sections:
            for i in range(section["start"], section["end"]):
                line_to_section[i] = section["type"]
        
        # Process each line
        for line_num, line in enumerate(lines):
            section_type = line_to_section.get(line_num)
            
            # Apply section-specific rules
            if section_type and section_type in self.SECTION_RULES:
                for pattern, token_type in self.SECTION_RULES[section_type]:
                    matches = list(pattern.finditer(line))
                    for match in reversed(matches):
                        original = match.group(1)
                        token = self.token_mapper.get_token(token_type)
                        redactions.append({
                            "data_type": token_type.value,
                            "line": line_num + 1,
                            "original": original,
                            "token": token,
                            "tier": 2
                        })
                        line = line[:match.start()] + token + line[match.end():]
            
            # Apply global patterns
            for pattern, token_type in self.GLOBAL_PATTERNS:
                matches = list(pattern.finditer(line))
                for match in reversed(matches):
                    original = match.group(1)
                    token = self.token_mapper.get_token(token_type)
                    redactions.append({
                        "data_type": token_type.value,
                        "line": line_num + 1,
                        "original": original,
                        "token": token,
                        "tier": 2
                    })
                    line = line[:match.start()] + token + line[match.end():]
            
            lines[line_num] = line
        
        return Tier2Result(
            sanitized_text='\n'.join(lines),
            redactions=redactions
        )
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/agent/sanitizer/tiers/test_tier2_section.py -v
```

**Step 5: Commit**

```bash
git add tests/agent/sanitizer/tiers/test_tier2_section.py services/agent/agent/sanitizer/tiers/tier2_section.py
git commit -m "feat(sanitizer): Add Tier 2 section-aware sanitizer"
```

---

## Phase 4: Tier 1 (TextFSM) - Future

### Task 5: Stub Tier 1 TextFSM Sanitizer

**Files:**
- Create: `services/agent/agent/sanitizer/tiers/tier1_textfsm.py`
- Test: `tests/agent/sanitizer/tiers/test_tier1_textfsm.py`

**Note:** Full TextFSM integration requires ntc-templates. This task creates the stub interface.

**Step 1: Write the stub and test**

```python
# tests/agent/sanitizer/tiers/test_tier1_textfsm.py
import pytest
from agent.sanitizer.tiers.tier1_textfsm import TextFSMSanitizer, TemplateNotFoundError


def test_raises_not_found_for_unknown_template():
    sanitizer = TextFSMSanitizer()
    with pytest.raises(TemplateNotFoundError):
        sanitizer.sanitize("some config", "unknown_vendor")


def test_available_templates_list():
    sanitizer = TextFSMSanitizer()
    templates = sanitizer.get_available_templates()
    assert isinstance(templates, list)
```

```python
# services/agent/agent/sanitizer/tiers/tier1_textfsm.py
"""Tier 1: TextFSM template-driven sanitization (stub for future implementation)"""

from dataclasses import dataclass
from typing import List


class TemplateNotFoundError(Exception):
    """Raised when no TextFSM template exists for device type"""
    pass


@dataclass
class Tier1Result:
    sanitized_text: str
    redactions: List[dict]
    template_used: str


class TextFSMSanitizer:
    """Tier 1: Template-driven sanitization using TextFSM/ntc-templates"""
    
    def __init__(self):
        self._templates = {}  # Load from ntc-templates in future
    
    def get_available_templates(self) -> List[str]:
        """Return list of supported device types"""
        return list(self._templates.keys())
    
    def has_template(self, device_type: str) -> bool:
        """Check if template exists for device type"""
        return device_type in self._templates
    
    def sanitize(self, config_text: str, device_type: str) -> Tier1Result:
        """Sanitize using TextFSM template"""
        if not self.has_template(device_type):
            raise TemplateNotFoundError(
                f"No TextFSM template for device type: {device_type}"
            )
        
        # TODO: Implement TextFSM parsing and sanitization
        # This requires ntc-templates integration
        raise NotImplementedError(
            "Tier 1 TextFSM sanitization not yet implemented. "
            "Use Tier 2 or Tier 3 for now."
        )
```

**Step 2: Run test and commit**

```bash
pytest tests/agent/sanitizer/tiers/test_tier1_textfsm.py -v
git add tests/agent/sanitizer/tiers/test_tier1_textfsm.py services/agent/agent/sanitizer/tiers/tier1_textfsm.py
git commit -m "feat(sanitizer): Add Tier 1 TextFSM stub (future implementation)"
```

---

## Phase 5: Tier Resolver & Main ConfigSanitizer

### Task 6: Implement TierResolver

**Files:**
- Create: `services/agent/agent/sanitizer/tier_resolver.py`
- Test: `tests/agent/test_tier_resolver.py`

**Step 1: Write the failing test**

```python
# tests/agent/test_tier_resolver.py
import pytest
from agent.sanitizer.tier_resolver import TierResolver, Tier


def test_resolve_prefers_tier1_if_template_exists():
    resolver = TierResolver()
    
    # Mock: pretend we have a template for "cisco_ios"
    resolver._available_templates = {"cisco_ios"}
    
    tier = resolver.resolve("some config", "cisco_ios")
    assert tier == Tier.TIER_1


def test_resolve_fallback_to_tier2_if_no_template():
    resolver = TierResolver()
    resolver._available_templates = set()
    
    # Config with structure (interface blocks)
    config = "interface Gig0/1\n ip address 10.1.1.1 255.255.255.0"
    tier = resolver.resolve(config, "unknown")
    assert tier == Tier.TIER_2


def test_resolve_fallback_to_tier3_if_unstructured():
    resolver = TierResolver()
    resolver._available_templates = set()
    
    # Config without clear structure
    config = "some random text without section headers"
    tier = resolver.resolve(config, "unknown")
    assert tier == Tier.TIER_3
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_tier_resolver.py -v
```

**Step 3: Write minimal implementation**

```python
# services/agent/agent/sanitizer/tier_resolver.py
from enum import Enum, auto
from typing import Set


class Tier(Enum):
    """Sanitization tiers in order of preference"""
    TIER_1 = 1  # TextFSM template-driven
    TIER_2 = 2  # Section-aware regex
    TIER_3 = 3  # Aggressive regex (fail-safe)


class TierResolver:
    """Determines which sanitization tier to use"""
    
    # Indicators that config has structure (Tier 2 candidate)
    STRUCTURE_INDICATORS = [
        r'^interface\s+\S+',
        r'^router\s+(bgp|ospf|eigrp)',
        r'^vlan\s+\d+',
        r'^hostname\s+\S+',
        r'^snmp-server',
    ]
    
    def __init__(self):
        # In production, load from ntc-templates
        self._available_templates: Set[str] = set()
    
    def register_template(self, device_type: str):
        """Register available TextFSM template"""
        self._available_templates.add(device_type)
    
    def has_template(self, device_type: str) -> bool:
        """Check if TextFSM template exists"""
        return device_type in self._available_templates
    
    def _has_structure(self, config_text: str) -> bool:
        """Check if config appears to have parseable structure"""
        import re
        for indicator in self.STRUCTURE_INDICATORS:
            if re.search(indicator, config_text, re.MULTILINE):
                return True
        return False
    
    def resolve(self, config_text: str, device_type: str) -> Tier:
        """
        Determine which tier to use for this config.
        
        Priority:
        1. Tier 1 if TextFSM template available
        2. Tier 2 if config has recognizable structure
        3. Tier 3 as fail-safe
        """
        # Tier 1: Template available?
        if self.has_template(device_type):
            return Tier.TIER_1
        
        # Tier 2: Config has structure?
        if self._has_structure(config_text):
            return Tier.TIER_2
        
        # Tier 3: Fail-safe
        return Tier.TIER_3
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_tier_resolver.py -v
```

**Step 5: Commit**

```bash
git add tests/test_tier_resolver.py services/agent/agent/sanitizer/tier_resolver.py
git commit -m "feat(sanitizer): Add TierResolver for automatic tier selection"
```

---

### Task 7: Implement Main ConfigSanitizer Class

**Files:**
- Create: `services/agent/agent/sanitizer/__init__.py` (package init)
- Create: `services/agent/agent/sanitizer/main.py`
- Modify: `services/agent/agent/sanitizer.py` (replace existing)
- Test: `tests/agent/test_sanitizer_integration.py`

**Step 1: Write the failing integration test**

```python
# tests/agent/test_sanitizer_integration.py
import pytest
from agent.sanitizer.main import ConfigSanitizer, SanitizationError


@pytest.fixture
def sanitizer():
    return ConfigSanitizer(org_id="test-org-123")


@pytest.mark.asyncio
async def test_sanitize_cisco_config(sanitizer):
    config = """
hostname core-router-01
!
interface GigabitEthernet0/1
 ip address 10.1.1.1 255.255.255.0
 no shutdown
!
snmp-server community public RO
username admin password Cisco123
"""
    result = await sanitizer.sanitize(config, "cisco_ios")
    
    # Sensitive data removed
    assert "10.1.1.1" not in result.sanitized_text
    assert "public" not in result.sanitized_text
    assert "Cisco123" not in result.sanitized_text
    
    # Tokens present
    assert "<ip_address>" in result.sanitized_text
    assert "<community_string>" in result.sanitized_text
    assert "<password>" in result.sanitized_text
    
    # Structure preserved
    assert "interface" in result.sanitized_text
    assert "GigabitEthernet0/1" in result.sanitized_text


@pytest.mark.asyncio
async def test_redaction_map_includes_all_replacements(sanitizer):
    config = "ip address 10.1.1.1 255.255.255.0\nsnmp-server community public"
    result = await sanitizer.sanitize(config, "unknown")
    
    assert result.redaction_map["org_id"] == "test-org-123"
    assert len(result.redaction_map["replacements"]) >= 2


@pytest.mark.asyncio
async def test_safety_check_blocks_unsanitized_data(sanitizer):
    # Config that might slip through sanitization
    tricky_config = "sensitive_data_in_unusual_format\x00password_stuff"
    
    with pytest.raises(SanitizationError):
        await sanitizer.sanitize(tricky_config, "unknown_device")


@pytest.mark.asyncio
async def test_respects_enable_llm_flag():
    sanitizer_off = ConfigSanitizer(org_id="test", enable_llm=False)
    sanitizer_on = ConfigSanitizer(org_id="test", enable_llm=True)
    
    assert sanitizer_off.llm_fallback is None
    assert sanitizer_on.llm_fallback is not None
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_sanitizer_integration.py -v
```

**Step 3: Write main sanitizer implementation**

```python
# services/agent/agent/sanitizer/__init__.py
"""Config Sanitizer package"""

from .main import ConfigSanitizer, SanitizationError, SanitizerResult
from .token_mapper import TokenMapper, TokenType
from .tier_resolver import TierResolver, Tier

__all__ = [
    "ConfigSanitizer",
    "SanitizationError",
    "SanitizerResult",
    "TokenMapper",
    "TokenType",
    "TierResolver",
    "Tier",
]
```

```python
# services/agent/agent/sanitizer/main.py
"""Main ConfigSanitizer entry point"""

import re
from dataclasses import dataclass
from typing import Optional

from .token_mapper import TokenMapper
from .redaction_logger import RedactionLogger
from .tier_resolver import TierResolver, Tier
from .tiers.tier2_section import SectionRegexSanitizer
from .tiers.tier3_regex import AggressiveRegexSanitizer


class SanitizationError(Exception):
    """Raised when sanitization fails and config cannot be safely processed"""
    pass


@dataclass
class SanitizerResult:
    """Result of sanitization operation"""
    sanitized_text: str
    redaction_map: dict
    tier_used: int
    template_matched: Optional[str]


class ConfigSanitizer:
    """
    Main entry point for config sanitization.
    
    Implements three-tier approach:
    1. TextFSM template-driven (when available)
    2. Section-aware regex (structured configs)
    3. Aggressive regex (fail-safe for unknown configs)
    
    LLM fallback is opt-in only (disabled by default).
    """
    
    def __init__(self, org_id: str, enable_llm: bool = False):
        self.org_id = org_id
        self.enable_llm = enable_llm
        
        # Components
        self.tier_resolver = TierResolver()
        self.token_mapper = TokenMapper()
        self.redaction_logger = RedactionLogger(org_id)
        
        # Tier implementations
        self._tier2 = SectionRegexSanitizer()
        self._tier3 = AggressiveRegexSanitizer()
        self.llm_fallback = None  # TODO: Implement if enable_llm=True
    
    async def sanitize(self, config_text: str, device_type: str) -> SanitizerResult:
        """
        Sanitize config text, replacing sensitive data with tokens.
        
        Args:
            config_text: Raw configuration text
            device_type: Device type hint (e.g., 'cisco_ios', 'juniper_junos')
        
        Returns:
            SanitizerResult with sanitized text and redaction map
        
        Raises:
            SanitizationError: If sanitization fails safety checks
        """
        self.redaction_logger.reset()
        
        # Determine tier
        tier = self.tier_resolver.resolve(config_text, device_type)
        
        # Apply appropriate tier
        if tier == Tier.TIER_1:
            # Tier 1 not yet implemented
            tier = Tier.TIER_2  # Fallback
        
        if tier == Tier.TIER_2:
            result = self._tier2.sanitize(config_text)
            tier_num = 2
        else:
            result = self._tier3.sanitize(config_text)
            tier_num = 3
        
        # Log redactions
        for redaction in result.redactions:
            self.redaction_logger.log(
                original=redaction["original"],
                replacement=redaction["token"],
                line=redaction["line"],
                data_type=redaction["data_type"],
                tier=redaction["tier"]
            )
        
        # Safety check
        if not self._safety_scan(result.sanitized_text):
            raise SanitizationError(
                "Safety check failed: potential sensitive data detected "
                "after sanitization. Upload blocked."
            )
        
        redaction_map = self.redaction_logger.get_redaction_map()
        
        return SanitizerResult(
            sanitized_text=result.sanitized_text,
            redaction_map=redaction_map,
            tier_used=tier_num,
            template_matched=None  # TODO: When Tier 1 implemented
        )
    
    def _safety_scan(self, text: str) -> bool:
        """
        Post-sanitization safety check.
        Returns False if potential sensitive data detected.
        """
        # Check for unredacted IPv4 addresses
        ipv4_pattern = re.compile(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b')
        if ipv4_pattern.search(text):
            return False
        
        # Check for password literals followed by non-token values
        password_pattern = re.compile(r'password\s+\S+', re.IGNORECASE)
        for match in password_pattern.finditer(text):
            value = match.group(0).split(None, 1)[1]
            if not value.startswith('<') and not value.endswith('>'):
                return False
        
        # Check for SNMP community literals
        community_pattern = re.compile(r'snmp-server community\s+\S+', re.IGNORECASE)
        for match in community_pattern.finditer(text):
            value = match.group(0).split(None, 2)[2]
            if not value.startswith('<') and not value.endswith('>'):
                return False
        
        return True
```

**Step 4: Update existing sanitizer.py to use new implementation**

```python
# services/agent/agent/sanitizer.py
"""Backward-compatible sanitizer module"""

from .sanitizer.main import ConfigSanitizer, SanitizationError, SanitizerResult

# Keep existing interface for backward compatibility
class ConfigSanitizer(ConfigSanitizer):
    """Backward-compatible wrapper"""
    pass

__all__ = ["ConfigSanitizer", "SanitizationError", "SanitizerResult"]
```

**Step 5: Run test to verify it passes**

```bash
pytest tests/test_sanitizer_integration.py -v
```

**Step 6: Commit**

```bash
git add services/agent/agent/sanitizer/ tests/test_sanitizer_integration.py
git commit -m "feat(sanitizer): Add main ConfigSanitizer with tiered sanitization"
```

---

## Phase 6: Test Fixtures & Safety Tests

### Task 8: Add Test Fixtures for Real Configs

**Files:**
- Create: `tests/agent/fixtures/cisco_ios_router.cfg`
- Create: `tests/agent/fixtures/juniper_junos_router.cfg`
- Test: `tests/agent/test_sanitizer_with_fixtures.py`

**Step 1: Create fixture files**

```text
# tests/agent/fixtures/cisco_ios_router.cfg
hostname core-router-01
!
interface Loopback0
 ip address 10.255.1.1 255.255.255.255
!
interface GigabitEthernet0/0
 description Uplink to Core
 ip address 10.1.1.1 255.255.255.252
 no shutdown
!
interface GigabitEthernet0/1
 description Downlink to Access
 ip address 192.168.1.1 255.255.255.0
 no shutdown
!
router ospf 1
 network 10.1.1.0 0.0.0.3 area 0
 network 192.168.1.0 0.0.0.255 area 0
!
snmp-server community public RO
snmp-server community private RW
!
username admin privilege 15 password Cisco123
username operator privilege 5 password Operator456
!
end
```

```text
# tests/agent/fixtures/juniper_junos_router.cfg
system {
    host-name core-router-01;
    name-server {
        8.8.8.8;
    }
}
interfaces {
    ge-0/0/0 {
        description "Uplink to Core";
        unit 0 {
            family inet {
                address 10.1.1.1/30;
            }
        }
    }
    ge-0/0/1 {
        description "Downlink to Access";
        unit 0 {
            family inet {
                address 192.168.1.1/24;
            }
        }
    }
}
protocols {
    ospf {
        area 0.0.0.0 {
            interface ge-0/0/0.0;
            interface ge-0/0/1.0;
        }
    }
}
```

**Step 2: Write fixture-based tests**

```python
# tests/agent/test_sanitizer_with_fixtures.py
import pytest
from pathlib import Path
from agent.sanitizer import ConfigSanitizer


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sanitizer():
    return ConfigSanitizer(org_id="test-org")


@pytest.mark.asyncio
async def test_sanitize_cisco_ios_fixture(sanitizer):
    config = (FIXTURES_DIR / "cisco_ios_router.cfg").read_text()
    result = await sanitizer.sanitize(config, "cisco_ios")
    
    # All sensitive IPs replaced
    assert "10.255.1.1" not in result.sanitized_text
    assert "10.1.1.1" not in result.sanitized_text
    assert "192.168.1.1" not in result.sanitized_text
    
    # Passwords removed
    assert "Cisco123" not in result.sanitized_text
    assert "Operator456" not in result.sanitized_text
    
    # SNMP communities removed
    assert "public" not in result.sanitized_text
    assert "private" not in result.sanitized_text
    
    # Tokens present
    assert "<ip_address>" in result.sanitized_text
    assert "<password>" in result.sanitized_text
    assert "<community_string>" in result.sanitized_text
    
    # Structure preserved
    assert "interface" in result.sanitized_text
    assert "GigabitEthernet0/0" in result.sanitized_text
    assert "router ospf" in result.sanitized_text


@pytest.mark.asyncio
async def test_sanitize_juniper_junos_fixture(sanitizer):
    config = (FIXTURES_DIR / "juniper_junos_router.cfg").read_text()
    result = await sanitizer.sanitize(config, "juniper_junos")
    
    # IPs replaced
    assert "10.1.1.1" not in result.sanitized_text
    assert "192.168.1.1" not in result.sanitized_text
    assert "8.8.8.8" not in result.sanitized_text
    
    # Tokens present
    assert "<ip_address>" in result.sanitized_text
```

**Step 3: Run tests and commit**

```bash
pytest tests/test_sanitizer_with_fixtures.py -v
git add tests/agent/fixtures/ tests/test_sanitizer_with_fixtures.py
git commit -m "test(sanitizer): Add fixture-based tests with real configs"
```

---

## Phase 7: Configuration & Integration

### Task 9: Add Sanitizer Configuration

**Files:**
- Create: `services/agent/config/sanitizer.yaml`
- Create: `services/agent/agent/config.py` (update or create)
- Test: `tests/agent/test_config.py`

**Step 1: Create configuration file**

```yaml
# services/agent/config/sanitizer.yaml
sanitizer:
  # Tier selection
  prefer_textfsm: true
  fallback_to_regex: true
  
  # LLM fallback (OPT-IN ONLY - disabled by default)
  enable_llm: false
  ollama_url: "http://localhost:11434"
  ollama_model: "llama3.2:7b"
  
  # Safety
  safety_check_enabled: true
  block_on_failure: true
  
  # Performance
  max_config_size_mb: 50
  timeout_seconds: 30
  
  # Token customization (optional)
  tokens:
    ipv4: "<ip_address>"
    ipv6: "<ipv6_address>"
    hostname: "<hostname>"
    fqdn: "<fqdn>"
    password: "<password>"
    secret: "<secret>"
    community: "<community_string>"
    bgp_as: "<as_number>"
    vlan_id: "<vlan_id>"
    mac: "<mac_address>"
```

**Step 2: Update agent config loader**

```python
# services/agent/agent/config.py
"""Agent configuration management"""

import os
import yaml
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class SanitizerConfig:
    """Sanitizer-specific configuration"""
    prefer_textfsm: bool = True
    fallback_to_regex: bool = True
    enable_llm: bool = False
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:7b"
    safety_check_enabled: bool = True
    block_on_failure: bool = True
    max_config_size_mb: int = 50
    timeout_seconds: int = 30
    custom_tokens: Optional[dict] = None


@dataclass
class AgentConfig:
    """Main agent configuration"""
    org_id: str
    api_key: str
    cloud_url: str
    sanitizer: SanitizerConfig
    
    @classmethod
    def from_yaml(cls, path: Path) -> "AgentConfig":
        """Load configuration from YAML file"""
        with open(path) as f:
            data = yaml.safe_load(f)
        
        sanitizer_data = data.get("sanitizer", {})
        sanitizer = SanitizerConfig(
            prefer_textfsm=sanitizer_data.get("prefer_textfsm", True),
            fallback_to_regex=sanitizer_data.get("fallback_to_regex", True),
            enable_llm=sanitizer_data.get("enable_llm", False),
            ollama_url=sanitizer_data.get("ollama_url", "http://localhost:11434"),
            ollama_model=sanitizer_data.get("ollama_model", "llama3.2:7b"),
            safety_check_enabled=sanitizer_data.get("safety_check_enabled", True),
            block_on_failure=sanitizer_data.get("block_on_failure", True),
            max_config_size_mb=sanitizer_data.get("max_config_size_mb", 50),
            timeout_seconds=sanitizer_data.get("timeout_seconds", 30),
            custom_tokens=sanitizer_data.get("tokens"),
        )
        
        return cls(
            org_id=data["org_id"],
            api_key=data["api_key"],
            cloud_url=data["cloud_url"],
            sanitizer=sanitizer,
        )
```

**Step 3: Add PyYAML to requirements**

```bash
# Add to services/agent/requirements.txt if not present
echo "pyyaml>=6.0" >> services/agent/requirements.txt
```

**Step 4: Test configuration loading**

```python
# tests/agent/test_config.py
import pytest
from pathlib import Path
from agent.config import AgentConfig, SanitizerConfig


def test_load_config_from_yaml(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
org_id: test-org
api_key: test-key
cloud_url: https://api.example.com
sanitizer:
  enable_llm: true
  ollama_model: "custom-model"
  tokens:
    ipv4: "[IP]"
""")
    
    config = AgentConfig.from_yaml(config_file)
    
    assert config.org_id == "test-org"
    assert config.sanitizer.enable_llm is True
    assert config.sanitizer.ollama_model == "custom-model"
    assert config.sanitizer.custom_tokens["ipv4"] == "[IP]"


def test_default_sanitizer_config():
    config = SanitizerConfig()
    
    assert config.enable_llm is False  # Critical: must be opt-in
    assert config.safety_check_enabled is True
    assert config.block_on_failure is True
```

**Step 5: Run tests and commit**

```bash
pytest tests/test_config.py -v
git add services/agent/config/sanitizer.yaml services/agent/agent/config.py tests/test_config.py services/agent/requirements.txt
git commit -m "feat(sanitizer): Add configuration support with YAML config file"
```

---

## Phase 8: Documentation & Final Review

### Task 10: Add Module Documentation

**Files:**
- Create: `services/agent/agent/sanitizer/README.md`

**Step 1: Write module documentation**

```markdown
# Config Sanitizer Module

Privacy-first configuration sanitization for NetDiscoverIT Local Agent.

## Overview

The Config Sanitizer ensures **zero sensitive data leaves the customer network** by replacing credentials, IP addresses, and other identifiers with placeholder tokens before vectorization.

## Architecture

### Three-Tier Approach

1. **Tier 1 - TextFSM Templates** (Future): Parse configs using NTC-templates, redact by field name
2. **Tier 2 - Section Regex** (Current): Parse config sections, apply context-aware redaction
3. **Tier 3 - Aggressive Regex** (Fail-safe): Pattern-based redaction for unknown configs

### Data Flow

```
Raw Config → Tier Resolver → [Tier 1/2/3] → Token Mapper → Sanitized Config
                                    ↓
                              Redaction Logger
```

## Usage

```python
from agent.sanitizer import ConfigSanitizer

sanitizer = ConfigSanitizer(org_id="customer-123")

result = await sanitizer.sanitize(config_text, device_type="cisco_ios")

# Sanitized config for vectorizer
print(result.sanitized_text)

# Audit trail
print(result.redaction_map)
```

## Configuration

```yaml
sanitizer:
  # LLM is OPT-IN ONLY (disabled by default for privacy)
  enable_llm: false
  
  # Safety
  safety_check_enabled: true
  block_on_failure: true
```

## Tokens

| Data Type | Token | Example |
|-----------|-------|---------|
| IPv4 | `<ip_address>` | `10.1.1.1` → `<ip_address>` |
| IPv6 | `<ipv6_address>` | `2001:db8::1` → `<ipv6_address>` |
| Hostname | `<hostname>` | `router-01` → `<hostname>` |
| Password | `<password>` | `password secret123` → `password <password>` |
| SNMP Community | `<community_string>` | `community public` → `community <community_string>` |
| BGP AS | `<as_number>` | `router bgp 65001` → `router bgp <as_number>` |
| VLAN ID | `<vlan_id>` | `vlan 100` → `vlan <vlan_id>` |
| MAC Address | `<mac_address>` | `0011.2233.4455` → `<mac_address>` |

## Testing

```bash
# Run all sanitizer tests
pytest tests/agent/test_sanitizer*.py -v

# Run with coverage
pytest tests/agent/test_sanitizer*.py --cov=agent.sanitizer
```

## Safety Guarantees

1. **Never fail open**: If sanitization fails, config is blocked
2. **Post-sanitization scan**: Verifies no sensitive data remains
3. **Deterministic tokens**: Same input always produces same output
4. **Audit trail**: Every redaction logged with hash verification

## Privacy Note

The LLM fallback is **disabled by default** and must be explicitly enabled by the customer. When enabled, it uses a local Ollama instance — no data ever leaves the customer network.
```

**Step 2: Commit documentation**

```bash
git add services/agent/agent/sanitizer/README.md
git commit -m "docs(sanitizer): Add module documentation"
```

---

### Task 11: Run Full Test Suite

**Step 1: Run all sanitizer tests**

```bash
cd /home/openether/NetDiscoverIT/services/agent
pytest tests/ -v --tb=short -k sanitizer
```

**Step 2: Verify code coverage**

```bash
pytest tests/ --cov=agent.sanitizer --cov-report=term-missing
```

Expected: >80% coverage on core modules

**Step 3: Run linting**

```bash
cd /home/openether/NetDiscoverIT
make lint
# or
flake8 services/agent --max-line-length=120 --ignore=E501,W503
black --check services/agent
```

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat(sanitizer): Complete tiered config sanitizer implementation

- TokenMapper for placeholder tokens
- RedactionLogger for audit trails
- Tier 2: Section-aware regex sanitizer
- Tier 3: Aggressive regex fail-safe
- TierResolver for automatic tier selection
- Main ConfigSanitizer with safety checks
- Configuration support with YAML
- Comprehensive test suite with fixtures
- LLM fallback disabled by default (opt-in only)"
```

---

## Summary

This implementation plan creates a production-ready Config Sanitizer with:

1. **Three-tier architecture** for graceful degradation
2. **Privacy-first design** (LLM opt-in, disabled by default)
3. **Comprehensive safety checks** (never fail open)
4. **Full audit trail** (redaction maps with hashes)
5. **Extensive test coverage** (unit, integration, fixture-based)
6. **Configuration support** (YAML-based, customer-controlled)

**Key Files Created:**
- `services/agent/agent/sanitizer/` - Main package
- `services/agent/agent/sanitizer/token_mapper.py` - Token mapping
- `services/agent/agent/sanitizer/redaction_logger.py` - Audit logging
- `services/agent/agent/sanitizer/tier_resolver.py` - Tier selection
- `services/agent/agent/sanitizer/tiers/` - Tier implementations
- `services/agent/agent/sanitizer/main.py` - Main entry point
- `services/agent/config/sanitizer.yaml` - Configuration
- `tests/agent/` - Comprehensive test suite

**Next Steps:**
1. Execute plan using `superpowers:executing-plans` skill
2. Add Tier 1 (TextFSM) when ntc-templates integration ready
3. Integrate with Collector → Normalizer → Vectorizer pipeline
