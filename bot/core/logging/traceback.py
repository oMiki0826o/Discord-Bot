"""
bot/core/logging/traceback.py

Modification():

- 提供 Discord Traceback 訊息切割功能。
- 統一使用 Logging Constants 的訊息大小限制。

本檔只負責 Traceback 文字處理。
"""

from __future__ import annotations

from bot.core.logging.constants import TRACEBACK_CHUNK_SIZE


# ── Traceback 切割 ──────────────────────

def split_traceback(text: str) -> list[str]:
    """將 Traceback 切割為 Discord 可接受的 Code Block 訊息。"""

    if not text:
        return []

    chunks: list[str] = []

    while text:
        chunk = text[:TRACEBACK_CHUNK_SIZE]
        text = text[TRACEBACK_CHUNK_SIZE:]

        chunks.append(
            f"```\n{chunk}\n```"
        )

    return chunks