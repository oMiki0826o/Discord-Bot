"""
bot/mod/ai/context/service.py

Modification():

- 將 scoped Recent History、History Search、Memory 與 Topic 收集為 ContextItem。
- 統一交由 ContextBudget 去重、排序與限制預算。
"""

from __future__ import annotations

import json

from ..history.models import EventScope, StoredEvent
from ..history.repository import EventRepository
from ..history.search import HistorySearchQuery, HistorySearchService
from ..memory.models import MemoryQuery, MemoryScopeType
from ..memory.service import MemoryService
from ..topics.models import TopicListQuery, TopicScopeType, TopicState
from ..topics.service import TopicService
from .budget import ContextBudget, estimate_tokens
from .models import ContextItem, ContextPack, ContextRequest, ContextSource


class ContextOrchestrator:
    def __init__(
        self,
        *,
        event_repository: EventRepository,
        history_search: HistorySearchService,
        memory_service: MemoryService,
        topic_service: TopicService,
        summary_service: object | None = None,
        budget: ContextBudget | None = None,
    ) -> None:
        self.event_repository = event_repository
        self.history_search = history_search
        self.memory_service = memory_service
        self.topic_service = topic_service
        self.summary_service = summary_service
        self.budget = budget or ContextBudget()

    def build(
        self,
        request: ContextRequest,
        *,
        selection_max_tokens: int | None = None,
        summary_trigger_tokens: int | None = None,
    ) -> ContextPack:
        items: list[ContextItem] = []
        recent = self.event_repository.recent(
            EventScope(
                user_id=request.user_id,
                channel_id=request.channel_id,
                conversation_id=request.conversation_id,
            ),
            limit=request.recent_limit,
        )
        items.extend(
            self._event_item(event, source=ContextSource.RECENT_HISTORY, relevance=0.60)
            for event in recent
            if event.event_id != request.current_event_id
        )
        recent_without_current = tuple(event for event in recent if event.event_id != request.current_event_id)
        raw_recent_tokens = sum(estimate_tokens(event.content) for event in recent_without_current)
        summary_limit = request.max_tokens if summary_trigger_tokens is None else summary_trigger_tokens
        if self.summary_service is not None and raw_recent_tokens > summary_limit:
            summary = self.summary_service.current_for_events(recent_without_current)
            if summary is not None:
                content = f"Conversation summary: {summary.content}"
                items.append(ContextItem(
                    item_id=f"summary:{request.conversation_id}:{summary.updated_at}", dedupe_key=f"summary:{request.conversation_id}",
                    source=ContextSource.SUMMARY, content=content, relevance=0.75, importance=4, confidence=1.0,
                    timestamp=summary.updated_at, token_cost=estimate_tokens(content),
                ))

        if request.history_query is not None:
            hits = self.history_search.search(HistorySearchQuery(
                user_id=request.user_id,
                channel_id=request.channel_id,
                query=request.history_query,
            ))
            available_hits = tuple(
                hit
                for hit in hits
                if hit.event.event_id != request.current_event_id
            )
            best_score = max(
                (hit.score for hit in available_hits),
                default=0.0,
            )
            for hit in available_hits:
                relative_score = (
                    0.0
                    if best_score <= 0.0
                    else hit.score / best_score
                )
                items.append(self._event_item(
                    hit.event,
                    source=ContextSource.HISTORY_SEARCH,
                    relevance=min(0.95, 0.70 + 0.25 * relative_score),
                ))

        if request.include_memory:
            for scope_type, scope_id in (
                (MemoryScopeType.GLOBAL, request.user_id),
                (MemoryScopeType.CHANNEL, request.channel_id),
                (MemoryScopeType.CONVERSATION, request.conversation_id),
            ):
                memories = self.memory_service.find_active(MemoryQuery(
                    user_id=request.user_id,
                    scope_type=scope_type,
                    scope_id=scope_id,
                ))
                for memory in memories:
                    content = (
                        f"Memory[{memory.memory_type}.{memory.memory_key}]: "
                        + json.dumps(memory.value, ensure_ascii=False, sort_keys=True)
                    )
                    items.append(ContextItem(
                        item_id=f"memory:{memory.memory_id}",
                        dedupe_key=f"memory:{memory.memory_id}",
                        source=ContextSource.MEMORY,
                        content=content,
                        relevance=0.85,
                        importance=memory.importance,
                        confidence=memory.confidence,
                        timestamp=memory.updated_at,
                        token_cost=estimate_tokens(content),
                    ))

        if request.include_topics:
            for scope_type, scope_id in (
                (TopicScopeType.GLOBAL, request.user_id),
                (TopicScopeType.CHANNEL, request.channel_id),
                (TopicScopeType.CONVERSATION, request.conversation_id),
            ):
                topics = self.topic_service.list(TopicListQuery(
                    user_id=request.user_id,
                    scope_type=scope_type,
                    scope_id=scope_id,
                ))
                items.extend(self._topic_item(topic) for topic in topics)

        selection_limit = request.max_tokens if selection_max_tokens is None else selection_max_tokens
        return self.budget.select(tuple(items), max_tokens=selection_limit)

    @staticmethod
    def _event_item(
        event: StoredEvent,
        *,
        source: ContextSource,
        relevance: float,
    ) -> ContextItem:
        content = f"{event.role.value}: {event.content}"
        return ContextItem(
            item_id=f"{source.value}:{event.event_id}",
            dedupe_key=f"event:{event.event_id}",
            source=source,
            content=content,
            relevance=relevance,
            importance=3,
            confidence=1.0,
            timestamp=event.created_at,
            token_cost=estimate_tokens(content),
        )

    @staticmethod
    def _topic_item(topic: TopicState) -> ContextItem:
        content = json.dumps(
            {
                "name": topic.name,
                "status": topic.status.value,
                "current_goal": topic.current_goal,
                "state": topic.state,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return ContextItem(
            item_id=f"topic:{topic.topic_id}",
            dedupe_key=f"topic:{topic.topic_id}",
            source=ContextSource.TOPIC,
            content=content,
            relevance=0.80,
            importance=4,
            confidence=1.0,
            timestamp=topic.updated_at,
            token_cost=estimate_tokens(content),
        )
