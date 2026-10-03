"""
bot/mod/ai/summary/service.py

Modification():

- Build and validate summaries against immutable Event ranges。
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from ..history.models import EventScope, StoredEvent
from ..history.repository import EventRepository
from .repository import ConversationSummary, SummaryRepository

_INSTRUCTION = "Summarize only verified conversation facts, decisions, pending work, and open questions. Do not invent traits or include secrets."


class SummaryService:
    def __init__(self, events: EventRepository, repository: SummaryRepository, *, provider: Any = None, model_candidates: tuple[str, ...] = ()) -> None:
        self.events = events
        self.repository = repository
        self.provider = provider
        self.model_candidates = model_candidates

    def current(self, user_id: str, channel_id: str, conversation_id: str) -> ConversationSummary | None:
        events = self._events(user_id, channel_id, conversation_id)
        return self.current_for_events(events)

    def current_for_events(self, events: tuple[StoredEvent, ...]) -> ConversationSummary | None:
        if not events:
            return None
        return self.repository.current(events[0].conversation_id, events[0].user_id, events[0].event_id, events[-1].event_id, self._hash(events))

    def save_text(self, user_id: str, channel_id: str, conversation_id: str, content: str, *, now: int) -> ConversationSummary:
        events = self._events(user_id, channel_id, conversation_id)
        if not events:
            raise LookupError("cannot summarize an empty conversation")
        return self.repository.save(conversation_id, user_id, events[0].event_id, events[-1].event_id, self._hash(events), content, now=now)

    async def rebuild(self, user_id: str, channel_id: str, conversation_id: str) -> ConversationSummary:
        if self.provider is None or not self.model_candidates:
            raise RuntimeError("summary provider is not configured")
        from ..provider.models import GenerationRequest, ProviderPolicy
        events = self._events(user_id, channel_id, conversation_id)
        if not events:
            raise LookupError("cannot summarize an empty conversation")
        transcript = "\n".join(f"{event.role.value}: {event.content}" for event in events)
        response = await self.provider.generate(GenerationRequest(request_id=f"summary:{conversation_id}:{time.time_ns()}", user_id=user_id, prompt=transcript, system_instruction=_INSTRUCTION, model_candidates=self.model_candidates, policy=ProviderPolicy(30, 1), max_output_tokens=800))
        return self.save_text(user_id, channel_id, conversation_id, response.text.strip(), now=int(time.time()))

    def _events(self, user_id: str, channel_id: str, conversation_id: str) -> tuple[StoredEvent, ...]:
        return self.events.recent(EventScope(user_id, channel_id, conversation_id), limit=200)

    @staticmethod
    def _hash(events: tuple[StoredEvent, ...]) -> str:
        digest = hashlib.sha256()
        for event in events:
            digest.update(event.event_id.encode("utf-8"))
            digest.update(b"\0")
            digest.update(event.content.encode("utf-8"))
            digest.update(b"\0")
        return digest.hexdigest()
