"""
TextFSM Parser for vendor-specific config parsing
"""

import logging
from typing import Dict
import textfsm

logger = logging.getLogger(__name__)


class TextFSMParser:
    TEMPLATE_MAP = {
        "cisco_ios": "cisco_ios_show_version.textfsm",
        "cisco_nxos": "cisco_nxos_show_version.textfsm",
        "juniper_junos": "junos_show_version.textfsm",
        "arista_eos": "arista_eos_show_version.textfsm",
        "hp_procurve": "hp_procurve_show_version.textfsm",
        "f5_bigip": "f5_bigip_version.textfsm",
    }

    def __init__(self, template_dir: str = None):
        self.template_dir = template_dir

    def parse(self, config: str, vendor: str) -> Dict:
        """Parse config using TextFSM template for the vendor"""
        try:
            template = self._load_template(vendor)
            if template is None:
                return {}

            result = template.ParseText(config)

            if not result or not result[0]:
                return {}

            parsed = {}
            headers = result.header if hasattr(result, 'header') else []

            for i, header in enumerate(headers):
                value = result[0][i] if result and len(result[0]) > i else ""
                if value and value != "None":
                    parsed[header.lower()] = value

            if parsed:
                parsed["_normalization_method"] = "textfsm"

            return parsed

        except Exception as e:
            logger.debug(f"TextFSM parsing failed for {vendor}: {e}")
            return {}

    def _load_template(self, vendor: str):
        """Load TextFSM template for the vendor"""
        template_name = self.TEMPLATE_MAP.get(vendor)
        if not template_name:
            return None

        try:
            import pkgutil
            import ntc_templates

            template_bytes = pkgutil.get_data("ntc_templates", f"textfsm_templates/{template_name}")
            if template_bytes:
                return textfsm.TextFSM(template_bytes)

        except Exception as e:
            logger.debug(f"Could not load ntc-templates for {template_name}: {e}")

        try:
            import os
            if self.template_dir:
                template_path = os.path.join(self.template_dir, template_name)
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                template_path = os.path.join(base_dir, "templates", template_name)

            if os.path.exists(template_path):
                with open(template_path, "r") as f:
                    return textfsm.TextFSM(f)

        except Exception as e:
            logger.debug(f"Could not load local template {template_name}: {e}")

        return None
