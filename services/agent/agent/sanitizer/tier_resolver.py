import re
from enum import Enum
from typing import Set


class Tier(Enum):
    """Sanitization tiers in order of preference"""

    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3


class TierResolver:
    """Determines which sanitization tier to use"""

    STRUCTURE_INDICATORS = [
        r"^interface\s+\S+",
        r"^router\s+(bgp|ospf|eigrp)",
        r"^vlan\s+\d+",
        r"^hostname\s+\S+",
        r"^snmp-server",
    ]

    def __init__(self):
        self._available_templates: Set[str] = set()

    def register_template(self, device_type: str):
        """Register available TextFSM template"""
        self._available_templates.add(device_type)

    def has_template(self, device_type: str) -> bool:
        """Check if TextFSM template exists"""
        return device_type in self._available_templates

    def _has_structure(self, config_text: str) -> bool:
        """Check if config appears to have parseable structure"""
        for indicator in self.STRUCTURE_INDICATORS:
            if re.search(indicator, config_text, re.MULTILINE):
                return True
        return False

    def resolve(self, config_text: str, device_type: str) -> Tier:
        """Determine which tier to use for this config.

        Priority:
        1. Tier 1 if TextFSM template available
        2. Tier 2 if config has recognizable structure
        3. Tier 3 as fail-safe
        """
        if self.has_template(device_type):
            return Tier.TIER_1

        if self._has_structure(config_text):
            return Tier.TIER_2

        return Tier.TIER_3
