"""
bot/mod/music/formatter.py

Modification():

- 提供 Music Module 的時間長度格式化。
- 將秒數轉換為播放器與收藏介面使用的顯示文字。

本檔負責 Music Module 專用的純格式化工具。
"""

from __future__ import annotations


# ── Duration ──────────────────────

def format_duration(seconds: int | float | None) -> str:
    """將秒數格式化為 M:SS 或 H:MM:SS。"""

    try:
        total_seconds = max(0, int(seconds or 0))
    except (TypeError, ValueError):
        total_seconds = 0

    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"

    return f"{minutes}:{secs:02d}"
