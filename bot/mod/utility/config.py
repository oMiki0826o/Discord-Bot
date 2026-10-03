"""
bot/mod/utility/config.py

Modification():

- 定義 Utility Module 的 Settings 名稱。
- 定義 MarkItDown 文件轉換功能的預設限制。

本檔負責 Utility Module 的非機密預設設定。
"""

from __future__ import annotations

from typing import Any

from bot.core.settings.schema import SettingRule


# ── Settings ──────────────────────

SETTINGS_NAME = "utility"

DEFAULT_SETTINGS: dict[str, Any] = {
    "markitdown": {
        "max_file_size_bytes": 25 * 1024 * 1024,
    },
}


SETTINGS_SCHEMA = {
    "markitdown.max_file_size_bytes": SettingRule(int, minimum=1),
}
