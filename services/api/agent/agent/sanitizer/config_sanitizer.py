from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

from agent.sanitizer.redaction_logger import RedactionLogger
from agent.sanitizer.tier_resolver import Tier, TierResolver
from agent.sanitizer.token_mapper import TokenMapper, TokenType
from agent.sanitizer.tiers.tier2_section import SectionRegexSanitizer
from agent.sanitizer.tiers.tier3_regex import AggressiveRegexSanitizer


class ConfigSanitizer:
    """Orchestrates tiered sanitization of network device configs.

    Tier 1 (Precise): Known token types via TextFSM templates
    Tier 2 (Heuristic): SectionRegexSanitizer for common sensitive fields
    Tier 3 (Catch-all): AggressiveRegexSanitizer as fail-safe
    """

    SENSITIVE_KEYS = frozenset([
        "password",
        "secret",
        "passwd",
        "credential",
        "auth",
        "api_key",
        "apikey",
        "token",
        "private_key",
        "key",
        "enable_password",
        "enable_secret",
    ])

    def __init__(
        self,
        org_id: str,
        enable_tier1: bool = True,
        enable_tier2: bool = True,
        enable_tier3: bool = True,
        custom_tokens: Optional[Dict[str, str]] = None,
    ):
        self.org_id = org_id
        self.enable_tier1 = enable_tier1
        self.enable_tier2 = enable_tier2
        self.enable_tier3 = enable_tier3

        self.token_mapper = TokenMapper(custom_tokens)
        self.redaction_logger = RedactionLogger(org_id)
        self.tier_resolver = TierResolver()
        self.tier2_sanitizer = SectionRegexSanitizer()
        self.tier3_sanitizer = AggressiveRegexSanitizer()

    def register_template(self, device_type: str) -> None:
        """Register a TextFSM template for Tier 1 sanitization."""
        self.tier_resolver.register_template(device_type)

    def sanitize(
        self,
        config: Union[str, dict],
        device_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sanitize configuration content.

        Args:
            config: Raw config as string or dict (JSON)
            device_type: Optional device type for TierResolver (e.g., "cisco_ios")

        Returns:
            dict with "sanitized" and "redaction_log" keys
        """
        self.redaction_logger.reset()

        if isinstance(config, dict):
            sanitized = self._sanitize_dict(config)
        else:
            sanitized = self._sanitize_text(config, device_type)

        return {
            "sanitized": sanitized,
            "redaction_log": self.redaction_logger.get_redaction_map(),
        }

    def _sanitize_text(self, text: str, device_type: Optional[str] = None) -> str:
        """Sanitize string config through all enabled tiers."""
        result = text
        tiers_used: List[int] = []

        if self.enable_tier1:
            result = self._apply_tier1(result, device_type)
            tiers_used.append(1)

        if self.enable_tier2:
            result, tier2_redactions = self._apply_tier2(result)
            for redaction in tier2_redactions:
                self.redaction_logger.log(
                    original=redaction.get("original", ""),
                    replacement=redaction["token"],
                    line=redaction["line"],
                    data_type=redaction["data_type"],
                    tier=redaction["tier"],
                )
            tiers_used.append(2)

        if self.enable_tier3:
            tier3_result = self.tier3_sanitizer.sanitize(result)
            result = tier3_result.sanitized_text
            for redaction in tier3_result.redactions:
                self.redaction_logger.log(
                    original=redaction.get("original", ""),
                    replacement=redaction["token"],
                    line=redaction["line"],
                    data_type=redaction["data_type"],
                    tier=redaction["tier"],
                )
            tiers_used.append(3)

        if tiers_used:
            self.redaction_logger.set_tiers_used(tiers_used)

        return result

    def _apply_tier1(
        self,
        text: str,
        device_type: Optional[str] = None,
    ) -> str:
        """Tier 1: Pass-through (TextFSM templates will be used in future)."""
        return text

    def _apply_tier2(self, text: str) -> tuple[str, List[Dict[str, Any]]]:
        """Tier 2: SectionRegexSanitizer for section-aware patterns."""
        tier2_result = self.tier2_sanitizer.sanitize(text)
        return tier2_result.sanitized_text, tier2_result.redactions

    def _sanitize_dict(self, data: Any) -> Any:
        """Recursively sanitize dict/JSON data."""
        if data is None:
            return None
        elif isinstance(data, dict):
            result = {}
            for key, value in data.items():
                if self._is_sensitive_key(key):
                    result[key] = self._sanitize_value(key, value)
                else:
                    result[key] = self._sanitize_dict(value)
            return result
        elif isinstance(data, list):
            return [self._sanitize_dict(item) for item in data]
        elif isinstance(data, str):
            return self._sanitize_text(data)
        else:
            return data

    def _sanitize_value(self, key: str, value: Any) -> Any:
        """Sanitize a value based on its key."""
        if value is None:
            return None
        elif isinstance(value, str):
            token_type = self._get_token_type_for_key(key)
            token = self.token_mapper.get_token(token_type)
            self.redaction_logger.log(
                original=value,
                replacement=token,
                line=0,
                data_type=token_type.value,
                tier=1,
            )
            return token
        elif isinstance(value, dict):
            return self._sanitize_dict(value)
        elif isinstance(value, list):
            return [self._sanitize_dict(item) for item in value]
        else:
            return value

    def _get_token_type_for_key(self, key: str) -> TokenType:
        """Determine the token type based on the key name."""
        key_lower = key.lower()
        if "password" in key_lower or "passwd" in key_lower:
            return TokenType.PASSWORD
        elif "secret" in key_lower or "token" in key_lower or "key" in key_lower:
            return TokenType.SECRET
        elif "community" in key_lower:
            return TokenType.COMMUNITY
        else:
            return TokenType.SECRET

    def _is_sensitive_key(self, key: str) -> bool:
        """Check if a key name indicates sensitive data."""
        key_lower = key.lower()
        return any(sensitive in key_lower for sensitive in self.SENSITIVE_KEYS)
