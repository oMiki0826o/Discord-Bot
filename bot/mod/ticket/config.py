"""
bot/mod/ticket/config.py

Modification():

- 定義 Ticket Module 的 Settings 名稱。
- 定義工單冷卻、數量限制、頻道名稱與封存類別預設值。
- 定義工單管理面板與確認介面的逾時時間。
- 定義工單主題與公開面板的預設文字。

本檔負責 Ticket Module 的非機密預設設定。
"""

from __future__ import annotations

from typing import Any

from bot.core.settings.schema import SettingRule


# ── Settings ──────────────────────

SETTINGS_NAME = "ticket"

DEFAULT_SETTINGS: dict[str, Any] = {
    "cooldown_seconds": 300,
    "max_per_user": 1,
    "channel_prefix": "ticket-",
    "category_name": "工單",
    "archive_category": "",
    "panel_title": "需要幫助嗎？",
    "panel_description": "點擊下方按鈕建立工單，我們的支援團隊將盡快協助您。",
    "management_timeout_seconds": 300,
    "member_selection_timeout_seconds": 180,
    "confirmation_timeout_seconds": 60,
    "close_delay_seconds": 5,
}

SETTINGS_SCHEMA = {
    "cooldown_seconds": SettingRule(int, minimum=0),
    "max_per_user": SettingRule(int, minimum=1),
    "management_timeout_seconds": SettingRule(int, minimum=1),
    "member_selection_timeout_seconds": SettingRule(int, minimum=1),
    "confirmation_timeout_seconds": SettingRule(int, minimum=1),
    "close_delay_seconds": SettingRule(int, minimum=0),
}


MAX_TOPIC_LENGTH = 100
