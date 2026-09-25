"""
bot/mod/message/config.py

Modification():

- 定義 Message Module 的 Settings 名稱。
- 定義訊息內容、附件數量與操作面板的預設限制。
- 定義 Message Module 使用的 Webhook 名稱。

本檔負責 Message Module 的非機密預設設定與固定常數。
"""

from __future__ import annotations

from typing import Any

from bot.core.settings.schema import SettingRule


# ── Settings ──────────────────────

SETTINGS_NAME = "message"

DEFAULT_SETTINGS: dict[str, Any] = {
    "require_management": False,
    "panel_timeout_seconds": 300,
    "admin_panel_timeout_seconds": 180,
    "plain_max_content_length": 1950,
    "webhook_max_content_length": 1900,
    "max_attachments": 3,
    "webhook_name": "Discord Bot",
}


SETTINGS_SCHEMA = {
    "panel_timeout_seconds": SettingRule(int, minimum=1),
    "admin_panel_timeout_seconds": SettingRule(int, minimum=1),
    "plain_max_content_length": SettingRule(int, minimum=1, maximum=2000),
    "webhook_max_content_length": SettingRule(int, minimum=1, maximum=2000),
    "max_attachments": SettingRule(int, minimum=0, maximum=10),
}
