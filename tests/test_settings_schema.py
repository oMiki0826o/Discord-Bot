"""
tests/test_settings_schema.py

Modification():

- 驗證 SettingRule 的型別、範圍、允許值與 null 規則。
- 驗證 bool 不會誤通過 int Schema。

本檔測試 Settings Schema 的核心驗證行為。
"""

from __future__ import annotations

import pytest

from bot.core.settings.schema import SettingRule


def test_integer_range() -> None:
    rule = SettingRule(int, minimum=0, maximum=100)
    rule.validate("music.volume", 50)
    with pytest.raises(ValueError):
        rule.validate("music.volume", 101)


def test_bool_is_not_integer() -> None:
    rule = SettingRule(int)
    with pytest.raises(ValueError):
        rule.validate("example.value", True)


def test_choices() -> None:
    rule = SettingRule(str, choices=frozenset({"owner", "channel"}))
    rule.validate("logging.destination", "owner")
    with pytest.raises(ValueError):
        rule.validate("logging.destination", "unknown")


def test_nullable_value() -> None:
    SettingRule(int, minimum=1, allow_none=True).validate("logging.channel_id", None)


def test_published_module_settings_match_schema() -> None:
    """發布版 JSON 應符合各模組目前宣告的預設值與 Schema。"""
    import importlib
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    module_names = (
        "guild",
        "logging",
        "message",
        "moderation",
        "music",
        "role",
        "ticket",
        "utility",
        "voice",
    )

    def resolve(data: dict, dotted_path: str):
        current = data
        for part in dotted_path.split("."):
            assert isinstance(current, dict) and part in current, f"缺少設定欄位：{dotted_path}"
            current = current[part]
        return current

    for module_name in module_names:
        config = importlib.import_module(f"bot.mod.{module_name}.config")
        path = root / "settings" / f"{config.SETTINGS_NAME}.json"
        data = json.loads(path.read_text(encoding="utf-8"))

        for key in config.DEFAULT_SETTINGS:
            assert key in data, f"{path.name} 缺少預設欄位：{key}"

        for dotted_path, rule in config.SETTINGS_SCHEMA.items():
            rule.validate(
                f"{config.SETTINGS_NAME}.{dotted_path}",
                resolve(data, dotted_path),
            )
