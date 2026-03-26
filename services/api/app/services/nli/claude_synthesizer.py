"""
NLI Claude Synthesizer

Makes a single async Anthropic API call with the assembled context and user question.
Extracts a structured JSON confidence block from Claude's response.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a network documentation assistant for NetDiscoverIT.
Answer questions using ONLY the provided network context below. Cite device hostnames when relevant.
If the context does not contain enough information to answer, say so explicitly — never invent device names or facts.
Keep answers concise (2–5 sentences unless a list is clearly more useful).

IMPORTANT: End every response with a JSON block on the very last line, with no trailing text:
{"confidence": <float 0.0-1.0>, "query_type": "<topology|security|compliance|changes|inventory>", "source_device_ids": ["<uuid>", ...]}

The confidence should reflect how well the context supports your answer (1.0 = fully supported, 0.0 = no relevant data).
The source_device_ids should list UUIDs of devices you cited in your answer."""

API_TIMEOUT = 15.0  # seconds


@dataclass
class SynthesisResult:
    answer: str
    confidence: float
    query_type: str
    source_device_ids: List[str]


class ClaudeSynthesizer:
    """Wraps the Anthropic API for single-call NLI synthesis."""

    def __init__(self, api_key: str, model: str) -> None:
        self.model = model
        self.available = bool(api_key)
        if self.available:
            self._client = AsyncAnthropic(api_key=api_key)

    def _parse_response(self, text: str) -> Tuple[str, float, str, List[str]]:
        """
        Extract answer text and JSON confidence block from Claude's response.
        The JSON block is expected to be the last line of the response.
        Falls back to confidence=0.5, query_type="inventory", source_ids=[] on parse failure.
        """
        lines = text.strip().split("\n")
        json_block = None

        # Try last line first
        for candidate in reversed(lines):
            candidate = candidate.strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                try:
                    json_block = json.loads(candidate)
                    answer_lines = [l for l in lines if l.strip() != candidate]
                    break
                except json.JSONDecodeError:
                    continue

        if json_block is None:
            return text.strip(), 0.5, "inventory", []

        answer = "\n".join(answer_lines).strip()
        confidence = min(1.0, max(0.0, float(json_block.get("confidence", 0.5))))
        query_type = json_block.get("query_type", "inventory")
        source_ids = json_block.get("source_device_ids", [])

        return answer, confidence, query_type, source_ids

    async def synthesize(self, question: str, context: str) -> SynthesisResult:
        """
        Call Claude with the assembled context and return a structured synthesis result.
        Caller must check `self.available` before calling.
        """
        user_message = f"Network context:\n{context}\n\nQuestion: {question}"

        response = await self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            timeout=API_TIMEOUT,
        )

        raw_text = response.content[0].text
        answer, confidence, query_type, source_ids = self._parse_response(raw_text)

        return SynthesisResult(
            answer=answer,
            confidence=confidence,
            query_type=query_type,
            source_device_ids=source_ids,
        )