"""
bot/mod/music/config.py

Modification():

- 定義 Music Module 的預設 Settings。
- 提供既有 get() / get_int() 設定鍵介面。
- 提供 Music Module 所需的設定讀取介面。

本檔負責 Music Module 的非機密設定。
"""

from __future__ import annotations

from typing import Any

from bot.core.settings.schema import SettingRule


SETTINGS_NAME = "music"

DEFAULT_SETTINGS: dict[str, Any] = {
    "default_volume_percent": 50,
    "voice_connect_timeout": 30,
    "stream_retry_attempts": 2,
    "stream_premature_end_seconds": 8,
    "idle_timeout_seconds": 180,
    "idle_disconnect_message": "超過三分鐘沒事了，我先離開了",
    "voice_health_check_interval_seconds": 15,
    "voice_reconnect_grace_seconds": 60,
    "max_queue_size": 50,
    "search_prefix": "ytsearch",
    "ffmpeg_path": "ffmpeg",
    "favorites_per_page": 10,
    "embed_colors": {},
    "loop_labels": {},
    "embed_footer": {
        "music": "音樂系統",
        "default": "Discord Bot",
    },
}


SETTINGS_SCHEMA = {
    "default_volume_percent": SettingRule(int, minimum=0, maximum=100),
    "voice_connect_timeout": SettingRule(int, minimum=1),
    "stream_retry_attempts": SettingRule(int, minimum=0, maximum=10),
    "stream_premature_end_seconds": SettingRule(int, minimum=0),
    "idle_timeout_seconds": SettingRule(int, minimum=0),
    "voice_health_check_interval_seconds": SettingRule(int, minimum=1),
    "voice_reconnect_grace_seconds": SettingRule(int, minimum=0),
    "max_queue_size": SettingRule(int, minimum=1),
    "favorites_per_page": SettingRule(int, minimum=1, maximum=25),
}

_runtime_settings: dict[str, Any] = DEFAULT_SETTINGS.copy()


def bind(configuration: dict[str, Any]) -> None:
    global _runtime_settings
    _runtime_settings = configuration


def _lookup(path: str, default: Any = None) -> Any:
    normalized = path
    if normalized.startswith("music."):
        normalized = normalized[len("music."):]

    if normalized.startswith("embed_footer."):
        normalized = normalized[len("embed_footer."):]
        current: Any = _runtime_settings.get("embed_footer", {})
        return current.get(normalized, default) if isinstance(current, dict) else default

    current: Any = _runtime_settings
    for part in normalized.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def get(path: str, default: Any = None) -> Any:
    return _lookup(path, default)


def get_int(path: str, default: int = 0) -> int:
    value = _lookup(path, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
