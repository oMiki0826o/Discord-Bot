"""
bot/mod/ai/retrieval/fusion.py

Modification():

- 建立可重現的 Reciprocal Rank Fusion。

本檔案用名次合併 FTS 與向量結果，不混用不同分數尺度。
"""

from __future__ import annotations


def rrf_fuse(rankings: tuple[tuple[str, ...], ...], *, k: int = 60) -> tuple[tuple[str, float], ...]:
    if k < 1:
        raise ValueError("rrf k must be positive")
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return tuple(sorted(scores.items(), key=lambda item: (-item[1], item[0])))

