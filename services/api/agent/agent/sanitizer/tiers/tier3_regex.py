from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

from agent.sanitizer.token_mapper import TokenMapper, TokenType


@dataclass
class Tier3Result:
    sanitized_text: str
    redactions: List[dict]


class AggressiveRegexSanitizer:
    """Tier 3: Catch-all regex-based sanitization (fail-safe).

    This sanitizer uses broad regex patterns to catch common sensitive data
    types that may not be caught by Tier 1 or Tier 2. It serves as a final
    safety net to ensure no sensitive data escapes sanitization.
    """
    
    # Patterns: (regex, token_type, description)
    PATTERNS: List[Tuple[re.Pattern, TokenType, str]] = [
        # IPv4 addresses
        (re.compile(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'),
         TokenType.IPV4, "IPv4 address"),

        # IPv6 addresses
        (re.compile(r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b'), TokenType.IPV6, "IPv6 address"),

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
                    groups = match.groups()
                    original = next((g for g in groups if g is not None), match.group(0)) if groups else match.group(0)
                    token = self.token_mapper.get_token(token_type)

                    redactions.append({
                        "data_type": token_type.value,
                        "line": line_num,
                        "original": original,
                        "token": token,
                        "tier": 3
                    })

                    if match.groups():
                        # Replace only the captured group, preserving prefix
                        # Find the last non-None group (the actual value to redact)
                        groups = match.groups()
                        group_index = next(
                            (i for i in range(len(groups), 0, -1) if groups[i-1] is not None),
                            0
                        )
                        sanitized_line = (
                            sanitized_line[:match.start(group_index)] +
                            token +
                            sanitized_line[match.end(group_index):]
                        )
                    else:
                        # No groups - replace entire match (for IP, MAC patterns)
                        sanitized_line = sanitized_line[:match.start()] + token + sanitized_line[match.end():]
            
            sanitized_lines.append(sanitized_line)
        
        return Tier3Result(
            sanitized_text='\n'.join(sanitized_lines),
            redactions=redactions
        )
