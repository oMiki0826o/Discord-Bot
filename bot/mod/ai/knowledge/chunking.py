"""
bot/mod/ai/knowledge/chunking.py

Modification():

- 建立 Markdown-aware 分塊，優先保留標題與段落邊界。
- 對過長段落使用單字與字元邊界分割，強制每塊大小上限。

本檔只處理文字分塊，不負責資料庫或 Embedding。
"""

from __future__ import annotations

import re

_HEADING = re.compile(r"^#{1,6}\s+\S")
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")


def chunk_markdown(markdown: str, *, max_chars: int = 2_000) -> tuple[str, ...]:
    """將 Markdown 依 section/paragraph 分成可檢索的穩定文字塊。"""

    if max_chars < 32:
        raise ValueError("max_chars must be at least 32")
    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return ()

    sections: list[str] = []
    current: list[str] = []
    for line in normalized.splitlines():
        if _HEADING.match(line) and current:
            sections.append("\n".join(current).strip())
            current = []
        current.append(line.rstrip())
    if current:
        sections.append("\n".join(current).strip())

    chunks: list[str] = []
    for section in sections:
        pending = ""
        for paragraph in _PARAGRAPH_BREAK.split(section):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            for piece in _split_oversized(paragraph, max_chars=max_chars):
                candidate = piece if not pending else f"{pending}\n\n{piece}"
                if len(candidate) <= max_chars:
                    pending = candidate
                else:
                    chunks.append(pending)
                    pending = piece
        if pending:
            chunks.append(pending)
    return tuple(chunks)


def _split_oversized(text: str, *, max_chars: int) -> tuple[str, ...]:
    if len(text) <= max_chars:
        return (text,)

    pieces: list[str] = []
    pending = ""
    for token in text.split():
        if len(token) > max_chars:
            if pending:
                pieces.append(pending)
                pending = ""
            pieces.extend(token[index:index + max_chars] for index in range(0, len(token), max_chars))
            continue
        candidate = token if not pending else f"{pending} {token}"
        if len(candidate) <= max_chars:
            pending = candidate
        else:
            pieces.append(pending)
            pending = token
    if pending:
        pieces.append(pending)
    return tuple(pieces)
