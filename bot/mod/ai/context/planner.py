"""
bot/mod/ai/context/planner.py

Modification():

- 建立基礎 AI 的決定式 Context Planner。
- 依 Router 意圖安全收集 Memory、History、Topic、Knowledge、Public Profile 與 Channel Context。
- 將所有來源重新交給單一 token budget 排序。

本檔不允許模型指定 private user/channel scope。
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any

from .budget import ContextBudget, estimate_tokens
from .models import ContextItem, ContextPack, ContextRequest, ContextSource

_PROFILE_CUES = (
    "是怎樣的人", "是怎麼樣的人", "是誰", "誰是", "這個人",
    "what is this person like", "who is", "public profile",
)
_FOLLOW_UP_CUES = (
    "這個", "這種", "這件", "那個", "上面", "前面", "剛剛", "繼續",
    "為什麼會", "怎麼會", "它", "他", "她", "該怎麼",
)


class BasicContextPlanner:
    def __init__(
        self,
        *,
        context: Any,
        profiles: Any = None,
        retrieval: Any = None,
        manual_memory: Any = None,
        channel_reader: Any = None,
        budget: ContextBudget | None = None,
    ) -> None:
        self.context = context
        self.profiles = profiles
        self.retrieval = retrieval
        self.manual_memory = manual_memory
        self.channel_reader = channel_reader
        self.budget = budget or ContextBudget()

    async def build(
        self,
        request: ContextRequest,
        *,
        prompt: str,
        route: Any,
        initial_context: tuple[str, ...],
    ) -> ContextPack:
        collection_request = replace(
            request,
            history_query=prompt if route.wants_history else None,
            include_memory=route.wants_memory,
            include_topics=route.wants_topic,
        )
        base = self.context.build(
            collection_request,
            selection_max_tokens=1_000_000,
            summary_trigger_tokens=request.max_tokens,
        )
        items = list(base.items)
        # Standalone questions must not inherit a chain of unverified model
        # answers merely because they were sent in the same Discord channel.
        # Explicit history requests and clear follow-ups retain their scoped
        # conversation context.
        if not route.wants_history and not _is_follow_up(prompt):
            items = [
                item for item in items
                if item.source is not ContextSource.RECENT_HISTORY
            ]
        items.extend(
            self._item(
                item_id=f"initial:{index}",
                source=ContextSource.INITIAL,
                content=content,
                relevance=1.0,
                importance=5,
            )
            for index, content in enumerate(initial_context)
            if content.strip()
        )

        # Owner-maintained JSON is a separate, directly re-read source.  It is
        # intentionally not put through the Evidence-based automatic memory DB.
        if route.wants_memory and self.manual_memory is not None:
            for index, record in enumerate(self.manual_memory.search(
                user_id=request.user_id,
                query=prompt,
                limit=20,
            )):
                value = record.get("value") if isinstance(record, dict) else record.value
                memory_type = record.get("type", "manual_memory") if isinstance(record, dict) else record.memory_type
                key = record.get("key", str(index)) if isinstance(record, dict) else record.key
                importance = record.get("importance", 3) if isinstance(record, dict) else record.importance
                source_file = record.get("source_file", "") if isinstance(record, dict) else record.source_file
                content = json.dumps({
                    "type": memory_type,
                    "key": key,
                    "value": value,
                    "source_file": source_file,
                }, ensure_ascii=False, sort_keys=True)
                items.append(self._item(
                    item_id=f"manual-memory:{source_file}:{key}:{index}",
                    source=ContextSource.MANUAL_MEMORY,
                    content=content,
                    relevance=0.9,
                    importance=importance,
                ))

        if route.wants_public_profile and self.profiles is not None:
            query = _profile_query(prompt)
            for user_id, profile in self.profiles.search(query, limit=10):
                content = json.dumps(
                    {"user_id": user_id, "public_profile": profile},
                    ensure_ascii=False,
                    sort_keys=True,
                )
                items.append(self._item(
                    item_id=f"profile:{user_id}",
                    source=ContextSource.PUBLIC_PROFILE,
                    content=content,
                    relevance=0.9,
                    importance=4,
                ))

        if route.wants_knowledge and self.retrieval is not None:
            for hit in await self.retrieval.search_knowledge(prompt, limit=6):
                items.append(self._item(
                    item_id=f"knowledge:{hit.chunk.chunk_id}",
                    source=ContextSource.KNOWLEDGE,
                    content=hit.chunk.content,
                    relevance=0.85,
                    importance=4,
                ))

        if route.wants_channel_context and self.channel_reader is not None:
            messages = await self.channel_reader(request.user_id, request.channel_id, prompt)
            for index, message in enumerate(messages):
                content = json.dumps(message, ensure_ascii=False, sort_keys=True)
                items.append(self._item(
                    item_id=f"channel:{message.get('message_id', index)}",
                    source=ContextSource.CHANNEL_CONTEXT,
                    content=content,
                    relevance=0.8,
                    importance=3,
                ))

        return self.budget.select(tuple(items), max_tokens=request.max_tokens)

    @staticmethod
    def _item(
        *,
        item_id: str,
        source: ContextSource,
        content: str,
        relevance: float,
        importance: int,
    ) -> ContextItem:
        return ContextItem(
            item_id=item_id,
            dedupe_key=item_id,
            source=source,
            content=content,
            relevance=relevance,
            importance=importance,
            confidence=1.0,
            timestamp=0,
            token_cost=estimate_tokens(content),
        )


def _profile_query(prompt: str) -> str:
    value = prompt.strip()
    folded = value.casefold()
    for cue in _PROFILE_CUES:
        index = folded.find(cue.casefold())
        if index >= 0:
            value = value[:index] + value[index + len(cue):]
            folded = value.casefold()
    value = re.sub(r"[<@!>?？,，.。、:：]", " ", value)
    return " ".join(value.split()) or prompt.strip()


def _is_follow_up(prompt: str) -> bool:
    value = prompt.strip().casefold()
    return len(value) <= 4 or any(cue in value for cue in _FOLLOW_UP_CUES)
