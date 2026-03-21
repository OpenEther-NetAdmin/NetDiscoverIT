import re
from typing import Any, Union

from agent.sanitizer.redaction_logger import RedactionLogger
from agent.sanitizer.token_mapper import TokenMapper, TokenType
from agent.sanitizer.tiers.tier3_regex import AggressiveRegexSanitizer


class ConfigSanitizer:
    """Orchestrates tiered sanitization of network device configs.

    Tier 1 (Precise): Known token types via TokenMapper (pass-through)
    Tier 2 (Heuristic): Additional regex for common sensitive fields
    Tier 3 (Catch-all): AggressiveRegexSanitizer
    """

    TIER2_PATTERNS = [
        (re.compile(r"AKIA[0-9A-Z]{16}"), TokenType.SECRET, "AWS Access Key"),
        (
            re.compile(r"-----BEGIN [A-Z]+ PRIVATE KEY-----"),
            TokenType.SECRET,
            "SSH Key",
        ),
        (
            re.compile(
                r'api[_-]?key["\s:=]+["\']?([a-zA-Z0-9_\-]{16,})["\']?', re.IGNORECASE
            ),
            TokenType.SECRET,
            "API Key",
        ),
        (re.compile(r"Bearer\s+([a-zA-Z0-9_\-\.]+)"), TokenType.SECRET, "Bearer Token"),
        (
            re.compile(r"Authorization:\s*Basic\s+([a-zA-Z0-9+/=]+)"),
            TokenType.SECRET,
            "Basic Auth",
        ),
        (
            re.compile(r"enable\s+password\s+(\S+)", re.IGNORECASE),
            TokenType.PASSWORD,
            "Enable Password",
        ),
    ]

    SENSITIVE_KEYS = frozenset(
        [
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
        ]
    )

    def __init__(
        self,
        org_id: str,
        enable_tier1: bool = True,
        enable_tier2: bool = True,
        enable_tier3: bool = True,
    ):
        self.org_id = org_id
        self.enable_tier1 = enable_tier1
        self.enable_tier2 = enable_tier2
        self.enable_tier3 = enable_tier3

        self.token_mapper = TokenMapper()
        self.redaction_logger = RedactionLogger(org_id)
        self.tier3_sanitizer = AggressiveRegexSanitizer()

    def sanitize(self, config: Union[str, dict]) -> dict:
        """Sanitize configuration content.

        Args:
            config: Raw config as string or dict (JSON)

        Returns:
            dict with "sanitized" and "redaction_log" keys
        """
        self.redaction_logger.reset()

        if isinstance(config, dict):
            sanitized = self._sanitize_dict(config)
        else:
            sanitized = self._sanitize_text(config)

        return {
            "sanitized": sanitized,
            "redaction_log": self.redaction_logger.get_redaction_map(),
        }

    def _sanitize_text(self, text: str) -> str:
        """Sanitize string config through all enabled tiers."""
        result = text

        if self.enable_tier1:
            result = self._apply_tier1(result)

        if self.enable_tier2:
            result = self._apply_tier2(result)

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

        return result

    def _apply_tier1(self, text: str) -> str:
        """Tier 1: Pass-through (TokenMapper handles known types)."""
        return text

    def _apply_tier2(self, text: str) -> str:
        """Tier 2: Heuristic regex for common sensitive patterns."""
        lines = text.split("\n")
        sanitized_lines = []

        for line_num, line in enumerate(lines, 1):
            sanitized_line = line

            for pattern, token_type, description in self.TIER2_PATTERNS:
                matches = list(pattern.finditer(sanitized_line))
                for match in reversed(matches):
                    groups = match.groups()
                    original = (
                        next((g for g in groups if g is not None), match.group(0))
                        if groups
                        else match.group(0)
                    )
                    token = self.token_mapper.get_token(token_type)

                    if match.groups():
                        groups = match.groups()
                        group_index = next(
                            (
                                i
                                for i in range(len(groups), 0, -1)
                                if groups[i - 1] is not None
                            ),
                            0,
                        )
                        sanitized_line = (
                            sanitized_line[: match.start(group_index)]
                            + token
                            + sanitized_line[match.end(group_index):]
                        )
                    else:
                        sanitized_line = (
                            sanitized_line[:match.start()]
                            + token
                            + sanitized_line[match.end():]
                        )

                    self.redaction_logger.log(
                        original=original,
                        replacement=token,
                        line=line_num,
                        data_type=token_type.value,
                        tier=2,
                    )

            sanitized_lines.append(sanitized_line)

        return "\n".join(sanitized_lines)

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
