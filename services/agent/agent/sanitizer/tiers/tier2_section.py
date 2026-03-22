import re
from dataclasses import dataclass
from typing import Dict, List

from agent.sanitizer.token_mapper import TokenMapper, TokenType


@dataclass
class Tier2Result:
    sanitized_text: str
    redactions: List[dict]


class SectionRegexSanitizer:
    """Tier 2: Section-aware regex sanitization"""

    SECTION_PATTERNS = {
        "interface": re.compile(r"^interface\s+(\S+)", re.MULTILINE),
        "router_bgp": re.compile(r"^router\s+bgp\s+(\d+)", re.MULTILINE),
        "router_ospf": re.compile(r"^router\s+ospf\s+(\d+)", re.MULTILINE),
        "snmp_server": re.compile(r"^snmp-server", re.MULTILINE),
        "username": re.compile(r"^username\s+\S+", re.MULTILINE),
    }

    SECTION_RULES = {
        "interface": [
            (re.compile(r"ip address\s+(\d+\.\d+\.\d+\.\d+)"), TokenType.IPV4),
            (re.compile(r"ip address\s+([0-9a-fA-F:]+)"), TokenType.IPV6),
        ],
        "router_bgp": [
            (re.compile(r"neighbor\s+(\d+\.\d+\.\d+\.\d+)"), TokenType.IPV4),
            (re.compile(r"bgp\s+(\d+)"), TokenType.BGP_AS),
        ],
        "username": [
            (re.compile(r"password\s+(\S+)"), TokenType.PASSWORD),
            (re.compile(r"secret\s+(\S+)"), TokenType.SECRET),
        ],
    }

    GLOBAL_PATTERNS = [
        (re.compile(r"snmp-server community\s+(\S+)"), TokenType.COMMUNITY),
        (re.compile(r"hostname\s+(\S+)"), TokenType.HOSTNAME),
    ]

    def __init__(self):
        self.token_mapper = TokenMapper()

    def _detect_sections(self, config_text: str) -> List[Dict]:
        """Detect config sections and their positions"""
        sections = []
        lines = config_text.split("\n")
        current_section = None
        start_line = 0

        for i, line in enumerate(lines):
            section_found = False
            for section_type, pattern in self.SECTION_PATTERNS.items():
                if pattern.match(line):
                    if current_section:
                        sections.append(
                            {
                                "type": current_section,
                                "start": start_line,
                                "end": i,
                            }
                        )
                    current_section = section_type
                    start_line = i
                    section_found = True
                    break
            if not section_found and line.strip() == "!" and current_section:
                sections.append(
                    {
                        "type": current_section,
                        "start": start_line,
                        "end": i,
                    }
                )
                current_section = None

        if current_section:
            sections.append(
                {
                    "type": current_section,
                    "start": start_line,
                    "end": len(lines),
                }
            )

        return sections

    def sanitize(self, config_text: str) -> Tier2Result:
        """Sanitize using section-aware rules"""
        lines = config_text.split("\n")
        sections = self._detect_sections(config_text)
        redactions = []

        line_to_section = {}
        for section in sections:
            for i in range(section["start"], section["end"]):
                line_to_section[i] = section["type"]

        for line_num, line in enumerate(lines):
            section_type = line_to_section.get(line_num)

            if section_type and section_type in self.SECTION_RULES:
                for pattern, token_type in self.SECTION_RULES[section_type]:
                    matches = list(pattern.finditer(line))
                    for match in reversed(matches):
                        original = match.group(1)
                        token = self.token_mapper.get_token(token_type)
                        redactions.append(
                            {
                                "data_type": token_type.value,
                                "line": line_num + 1,
                                "original": original,
                                "token": token,
                                "tier": 2,
                            }
                        )
                        line = line[: match.start()] + token + line[match.end() :]

            for pattern, token_type in self.GLOBAL_PATTERNS:
                matches = list(pattern.finditer(line))
                for match in reversed(matches):
                    original = match.group(1)
                    token = self.token_mapper.get_token(token_type)
                    redactions.append(
                        {
                            "data_type": token_type.value,
                            "line": line_num + 1,
                            "original": original,
                            "token": token,
                            "tier": 2,
                        }
                    )
                    line = line[: match.start()] + token + line[match.end() :]

            lines[line_num] = line

        return Tier2Result(sanitized_text="\n".join(lines), redactions=redactions)
