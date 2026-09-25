"""
bot/mod/basic/help/models.py

Modification():

- 定義 Help Command 資料結構。
- 定義 Help 分類資料結構。
- 定義 Help 分頁資料結構。

本檔只負責 Help 系統的資料模型，
不處理 Discord UI、Command 掃描或指令執行。
"""

from __future__ import annotations

from dataclasses import dataclass


# ── Help Entry ──────────────────────

@dataclass(slots=True, frozen=True)
class HelpEntry:
    """單一 Slash Command 的 Help 資訊。"""

    name: str
    description: str


# ── Help Page ──────────────────────

@dataclass(slots=True, frozen=True)
class HelpPage:
    """單一 Help 分頁。"""

    category: str
    entries: tuple[HelpEntry, ...]


# ── Help Category ──────────────────────

@dataclass(slots=True, frozen=True)
class HelpCategory:
    """單一 Help 分類及其所有分頁。"""

    name: str
    pages: tuple[HelpPage, ...]