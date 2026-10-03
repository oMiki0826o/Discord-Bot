"""
bot/mod/moderation/config.py

Modification():

- 定義 Moderation Module 的 Settings 名稱。
- 定義禁言時長、DM 通知與操作面板的預設設定。
- 定義管理紀錄查詢數量與輸入限制。

本檔負責 Moderation Module 的非機密預設設定與固定限制。
"""

from __future__ import annotations

from typing import Any

from bot.core.settings.schema import SettingRule


# ── Settings ──────────────────────

SETTINGS_NAME = "moderation"

DEFAULT_SETTINGS: dict[str, Any] = {
    "default_mute_minutes": 10,
    "max_mute_minutes": 43200,
    "dm_target_on_warn": True,
    "dm_target_on_mute": False,
    "embed_footer": "Discord Bot",
    "panel_timeout_seconds": 300,
    "member_selection_timeout_seconds": 180,
    "confirmation_timeout_seconds": 30,
    "modlog_limit": 20,
}

SETTINGS_SCHEMA = {
    "default_mute_minutes": SettingRule(int, minimum=1),
    "max_mute_minutes": SettingRule(int, minimum=1),
    "panel_timeout_seconds": SettingRule(int, minimum=1),
    "member_selection_timeout_seconds": SettingRule(int, minimum=1),
    "confirmation_timeout_seconds": SettingRule(int, minimum=1),
    "modlog_limit": SettingRule(int, minimum=1, maximum=100),
}


MAX_REASON_LENGTH = 500
MAX_PURGE_AMOUNT = 100
MAX_BAN_DELETE_DAYS = 7
