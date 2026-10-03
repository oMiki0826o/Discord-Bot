"""
bot/mod/ai/prompt/composer.py

Modification():

- 依固定順序組裝 System、Persona 與 Background。
- 將 Context 保留為獨立 reference blocks，不提升為 system rules。
"""

from __future__ import annotations

from ..context.models import ContextPack, ContextSource
from .models import (
    PromptBundle,
    PromptContextBlock,
    PromptMessage,
    PromptRole,
    PromptSources,
)


class PromptComposer:
    def compose(
        self,
        *,
        sources: PromptSources,
        context: ContextPack,
        conversation: tuple[PromptMessage, ...],
        current_message: str,
        compact: bool = False,
    ) -> PromptBundle:
        system = sources.gemma_system if compact and sources.gemma_system.strip() else sources.system
        persona = sources.gemma_persona if compact and sources.gemma_persona.strip() else sources.persona
        background = sources.gemma_background if compact and sources.gemma_background.strip() else sources.background
        current = PromptMessage(PromptRole.USER, current_message)
        blocked_terms = (
            "# Blocked Terms\nDo not generate or repeat blocked terms unless "
            "the system explicitly requires a safety explanation: "
            + ", ".join(sources.blocked_words)
            if sources.blocked_words else ""
        )
        system_instruction = "\n\n".join((
            "# System Rules\n" + system,
            "# Moderation Rules\n" + sources.moderation_rules if sources.moderation_rules else "",
            blocked_terms,
            "# Persona\n" + persona,
            "# Background\n" + background,
        )).strip()
        conversation_sources = {
            ContextSource.RECENT_HISTORY,
            ContextSource.HISTORY_SEARCH,
        }
        # Selection is relevance-first, but conversation must be read in its
        # original order.  Reversing it makes pronouns such as「這／它」point
        # at an older topic and was the direct cause of topic drift.
        ordinary_items = [item for item in context.items if item.source not in conversation_sources]
        conversation_items = sorted(
            (item for item in context.items if item.source in conversation_sources),
            key=lambda item: (item.timestamp, item.item_id),
        )
        ordered_items = ordinary_items + conversation_items
        blocks = [
            PromptContextBlock(
                item_id=item.item_id,
                source=item.source,
                content=(
                    "Recent conversation (chronological; current user corrections override "
                    "earlier assistant replies; Historical assistant text is unverified and "
                    "must never be used as factual evidence without a reliable source):\n" + item.content
                    if index == len(ordinary_items) and item.source in conversation_sources
                    else item.content
                ),
                relevance=item.relevance,
                importance=item.importance,
                confidence=item.confidence,
                timestamp=item.timestamp,
            )
            for index, item in enumerate(ordered_items)
        ]
        reference_sources = (
            ("prompt:keywords", "Keywords (reference only): " + ", ".join(sources.keywords)),
            ("prompt:global_memory", "Global memory (reference only): " + "\n".join(sources.global_memory)),
        )
        for item_id, content in reference_sources:
            if content.rsplit(":", 1)[-1].strip():
                blocks.append(
                    PromptContextBlock(
                        item_id=item_id,
                        source=ContextSource.INITIAL,
                        content=content,
                        relevance=1.0,
                        importance=3,
                        confidence=1.0,
                        timestamp=0,
                    )
                )
        return PromptBundle(
            system_instruction=system_instruction,
            context_blocks=tuple(blocks),
            messages=conversation + (current,),
            context_used_tokens=context.used_tokens,
            context_omitted_count=context.omitted_count,
        )
