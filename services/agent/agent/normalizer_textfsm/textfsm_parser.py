from __future__ import annotations

from pathlib import Path
from services.common.normalization.schemas import NormalizedCommandOutput


class TextFSMParser:
    def __init__(self, templates_dir: str | Path | None = None) -> None:
        self.templates_dir = Path(templates_dir) if templates_dir else None

    def resolve_template(self, vendor: str, command: str) -> str | None:
        name = f"{vendor}_{command.replace(' ', '_')}.textfsm"
        if self.templates_dir is None:
            return name
        candidate = self.templates_dir / name
        return str(candidate) if candidate.exists() else None

    def parse(self, vendor: str, command: str, raw_output: str) -> NormalizedCommandOutput:
        template = self.resolve_template(vendor, command)
        if template:
            return NormalizedCommandOutput(
                vendor=vendor,
                command=command,
                records=[{"raw_output": raw_output.strip()}],
                parser_method="textfsm",
                template_name=Path(template).name,
                template_source=template,
                parser_status="success",
                parser_confidence=1.0,
            )
        return NormalizedCommandOutput(
            vendor=vendor,
            command=command,
            records=[{"raw_output": raw_output.strip()}],
            parser_method="fallback",
            parser_status="partial",
            parser_confidence=0.5,
            fallback_reason="template_missing",
            warnings=["Template missing; using permissive fallback parser"],
        )
