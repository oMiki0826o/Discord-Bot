"""
bot/mod/guild/config.py

Modification():

- 定義 Guild Module 的 Settings 名稱。
- 定義歡迎與離開訊息的預設範本。
- 定義成員日誌 Footer 與設定面板逾時時間。

本檔負責 Guild Module 的非機密預設設定。
"""

from __future__ import annotations

from typing import Any

from bot.core.settings.schema import SettingRule


# ── Settings ──────────────────────

SETTINGS_NAME = "guild"

DEFAULT_SETTINGS: dict[str, Any] = {
    "welcome_template": "歡迎 {user} 加入 **{guild}**！",
    "leave_template": "**{username}** 離開了 **{guild}**",
    "embed_footer": "Discord Bot",
    "panel_timeout_seconds": 300,
    "selection_timeout_seconds": 120,
    "confirmation_timeout_seconds": 60,
}


SETTINGS_SCHEMA = {
    "panel_timeout_seconds": SettingRule(int, minimum=1),
    "selection_timeout_seconds": SettingRule(int, minimum=1),
    "confirmation_timeout_seconds": SettingRule(int, minimum=1),
}
