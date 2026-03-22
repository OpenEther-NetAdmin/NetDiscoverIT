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
        self._templates = {}

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

        raise NotImplementedError(
            "Tier 1 TextFSM sanitization not yet implemented. "
            "Use Tier 2 or Tier 3 for now."
        )
