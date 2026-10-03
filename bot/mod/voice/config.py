"""
bot/mod/voice/config.py

Modification():

- 定義 Voice Module 的 Settings 名稱與預設值。
- 提供 Voice Module 的設定讀取介面。
- 保存 JTC 的全域 fallback 設定，不保存 Guild Runtime Data。

本檔負責 Voice Module 的非機密預設設定。
"""

from __future__ import annotations

from typing import Any

from bot.core.settings.schema import SettingRule


# ── Settings ──────────────────────

SETTINGS_NAME = "voice"

DEFAULT_SETTINGS: dict[str, Any] = {
    "jtc_channel_id": 0,
    "category_id": 0,
    "default_name_template": "{username} 的頻道",
    "default_limit": 0,
}


SETTINGS_SCHEMA = {
    "jtc_channel_id": SettingRule(int, minimum=0),
    "category_id": SettingRule(int, minimum=0),
    "default_limit": SettingRule(int, minimum=0, maximum=99),
}

_runtime_settings: dict[str, Any] = DEFAULT_SETTINGS.copy()


def bind(configuration: dict[str, Any]) -> None:
    """綁定 Core Settings Manager 載入後的 Voice 設定。"""

    global _runtime_settings
    _runtime_settings = configuration


def get_setting(key: str, default: Any = None) -> Any:
    """讀取指定設定鍵。"""

    prefix = "voice_channel."
    normalized = key[len(prefix):] if key.startswith(prefix) else key
    return _runtime_settings.get(normalized, default)
