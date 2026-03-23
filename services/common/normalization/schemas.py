from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class NormalizedCommandOutput(BaseModel):
    vendor: str
    command: str
    records: list[dict[str, Any]] = Field(default_factory=list)
    parser_method: Literal["textfsm", "fallback", "strict"]
    template_name: str | None = None
    template_source: str | None = None
    parser_status: Literal["success", "partial", "fallback", "error"] = "success"
    parser_confidence: float = 1.0
    fallback_reason: str | None = None
    warnings: list[str] = Field(default_factory=list)
    schema_version: str = "1.0"
    normalized_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
