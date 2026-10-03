"""
bot/mod/ai/background/extractor.py

Modification():

- 建立 Provider-backed Memory Candidate 擷取邊界。
- 只產生 Candidate payload，實際整併仍由 MemoryService 處理。

本檔案不讓模型直接修改 Memory State。
"""

from __future__ import annotations

import json
from typing import Any

from ..provider.models import GenerationRequest, ProviderPolicy

_INSTRUCTION = """Analyze the user message and return a JSON array of durable memory candidates only.
Each item must contain exactly: type, key, value, confidence, importance,
assertion_strength (tentative|observed|explicit), temporal_scope
(temporary|ongoing|permanent).
Only retain the user's explicit stable identity, durable preferences, long-running
project decisions, or an explicit request to remember something. Never store
technical questions, technical answers, game facts, explanations, model guesses,
or claims that require external verification. Do not store secrets, transient
chatter, assistant text, or unsupported guesses.
Return [] when nothing is worth remembering."""


class ProviderMemoryExtractor:
    def __init__(self, *, provider: Any, memory_service: Any, model_candidates: tuple[str, ...], mirror: Any = None, timeout_seconds: float = 15.0) -> None:
        self.provider = provider
        self.memory_service = memory_service
        self.model_candidates = model_candidates
        self.timeout_seconds = timeout_seconds
        self.mirror = mirror

    async def __call__(self, event: Any) -> None:
        response = await self.provider.generate(GenerationRequest(
            request_id=f"memory:{event.event_id}", user_id=event.user_id,
            prompt=event.content, system_instruction=_INSTRUCTION,
            model_candidates=self.model_candidates,
            policy=ProviderPolicy(self.timeout_seconds, 1, allow_fallback=False),
            max_output_tokens=1000,
        ))
        payload = self._parse_json(response.text)
        results = self.memory_service.process_extraction(event, payload)
        if self.mirror is not None and any(result.memory is not None for result in results):
            self.mirror.export_user(event.user_id)

    @staticmethod
    def _parse_json(text: str) -> object:
        value = text.strip()
        if value.startswith("```"):
            lines = value.splitlines()
            value = "\n".join(lines[1:-1])
            if value.lstrip().startswith("json"):
                value = value.lstrip()[4:].lstrip()
        if not value:
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        # A malformed model response must not make the durable background job
        # fail repeatedly.  Treat any valid but unexpected JSON shape as an
        # empty extraction; only arrays are valid memory candidates.
        return parsed if isinstance(parsed, list) else []
