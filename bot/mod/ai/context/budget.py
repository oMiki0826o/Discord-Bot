"""
bot/mod/ai/context/budget.py

Modification():

- 以 deterministic ranking、dedupe 與 hard budget 建立 ContextPack。
- 提供 Provider 尚未確定時的保守 UTF-8 token heuristic。
"""

from __future__ import annotations

from .models import ContextItem, ContextPack


def estimate_tokens(content: str) -> int:
    if not isinstance(content, str) or not content:
        raise ValueError("content 不得空白")
    return max(1, (len(content.encode("utf-8")) + 3) // 4)


class ContextBudget:
    def select(
        self,
        items: tuple[ContextItem, ...],
        *,
        max_tokens: int,
    ) -> ContextPack:
        if (
            not isinstance(max_tokens, int)
            or isinstance(max_tokens, bool)
            or max_tokens < 1
        ):
            raise ValueError("max_tokens 必須是正整數")

        ranked = sorted(
            items,
            key=lambda item: (
                -item.relevance,
                -item.importance,
                -item.confidence,
                -item.timestamp,
                item.item_id,
            ),
        )
        selected: list[ContextItem] = []
        seen: set[str] = set()
        used_tokens = 0
        omitted_count = 0

        for item in ranked:
            if item.dedupe_key in seen:
                omitted_count += 1
                continue
            seen.add(item.dedupe_key)
            if used_tokens + item.token_cost > max_tokens:
                omitted_count += 1
                continue
            selected.append(item)
            used_tokens += item.token_cost

        return ContextPack(
            items=tuple(selected),
            used_tokens=used_tokens,
            max_tokens=max_tokens,
            omitted_count=omitted_count,
        )
