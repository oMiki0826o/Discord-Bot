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
    "auto_reply": {
        "enabled": True,
        "regex_timeout_seconds": 0.05,
        "max_rules_per_guild": 100,
        "default_cooldown_seconds": 5.0,
    },
}


SETTINGS_SCHEMA = {
    "panel_timeout_seconds": SettingRule(int, minimum=1),
    "admin_panel_timeout_seconds": SettingRule(int, minimum=1),
    "plain_max_content_length": SettingRule(int, minimum=1, maximum=2000),
    "webhook_max_content_length": SettingRule(int, minimum=1, maximum=2000),
    "max_attachments": SettingRule(int, minimum=0, maximum=10),
    "auto_reply.regex_timeout_seconds": SettingRule(float, minimum=0.001, maximum=1.0),
    "auto_reply.max_rules_per_guild": SettingRule(int, minimum=1, maximum=1000),
    "auto_reply.default_cooldown_seconds": SettingRule(float, minimum=0.0, maximum=86400.0),
}
