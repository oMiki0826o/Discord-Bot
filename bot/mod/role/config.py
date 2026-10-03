"""
bot/mod/role/config.py

Modification():

- 定義 Role Module 的 Settings 名稱。
- 定義身分組面板的預設文字與互動逾時時間。
- 定義身分組按鈕與 Embed 欄位的限制。

本檔負責 Role Module 的非機密預設設定與固定限制。
"""

from __future__ import annotations

from typing import Any

from bot.core.settings.schema import SettingRule


# ── Settings ──────────────────────

SETTINGS_NAME = "role"

DEFAULT_SETTINGS: dict[str, Any] = {
    "panel_title": "身分組領取",
    "panel_description": "點擊下方按鈕以領取或移除身分組",
    "management_timeout_seconds": 300,
    "selection_timeout_seconds": 180,
    "confirmation_timeout_seconds": 60,
}

SETTINGS_SCHEMA = {
    "management_timeout_seconds": SettingRule(int, minimum=1),
    "selection_timeout_seconds": SettingRule(int, minimum=1),
    "confirmation_timeout_seconds": SettingRule(int, minimum=1),
}


MAX_PANEL_ROLES = 25
MAX_BUTTON_LABEL_LENGTH = 80
MAX_ROLE_DESCRIPTION_LENGTH = 100
MAX_PANEL_TITLE_LENGTH = 100
MAX_PANEL_DESCRIPTION_LENGTH = 300
EMBED_FIELD_VALUE_LIMIT = 1000
