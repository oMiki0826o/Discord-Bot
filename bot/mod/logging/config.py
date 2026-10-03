"""
bot/mod/logging/config.py

Modification():

- 定義 Logging Module 的 Settings 名稱。
- 定義錯誤通報功能的預設 Settings。
- 定義結束報告功能的預設 Settings。

本檔負責 Logging Module 的預設設定。
"""

from __future__ import annotations

from typing import Any

from bot.core.settings.schema import SettingRule


# ── Settings ──────────────────────

SETTINGS_NAME = "logging"

DEFAULT_SETTINGS: dict[str, Any] = {
    "error_reporting": {
        "enabled": True,
        "full_context": False,
        "destination": "owner",
        "channel_id": None,
    },
    "shutdown_report": {
        "send_log_file": True,
    },
}

SETTINGS_SCHEMA = {
    "error_reporting.destination": SettingRule(str, choices=frozenset({"owner", "channel"})),
    "error_reporting.channel_id": SettingRule(int, minimum=1, allow_none=True),
}
