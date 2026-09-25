"""
bot/core/settings/manager.py

Modification():

- 提供統一 JSON Settings 載入與存取。
- 支援 Module 註冊預設 Settings。
- 自動建立缺少的 Settings 檔案。
- 自動遞迴補齊缺少的預設欄位。
- 保留使用者既有 Settings 值。
- 支援 Settings 修改與持久化儲存。
- 支援單一或全部 Settings 重新載入。
- 依預設值與 Module Schema 驗證設定型別、範圍與允許值。

本檔負責非機密 Settings 的生命週期管理。
Token、API Key 等機密設定不由本系統管理。
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from bot.config import SETTINGS_DIR
from bot.core.settings.schema import SettingRule


# ── Settings Manager ──────────────────────

class SettingsManager:
    """管理 JSON Settings 的載入、預設值、修改與儲存。"""

    def __init__(
        self,
        settings_dir: Path = SETTINGS_DIR,
    ) -> None:
        self.settings_dir = settings_dir

        self._settings: dict[str, dict[str, Any]] = {}
        self._defaults: dict[str, dict[str, Any]] = {}
        self._schemas: dict[str, dict[str, SettingRule]] = {}

    # ── 路徑 ──────────────────────

    def _get_path(self, name: str) -> Path:
        """取得指定 Settings 的 JSON 路徑。"""

        return self.settings_dir / f"{name}.json"

    # ── 預設值合併 ──────────────────────

    @classmethod
    def _merge_defaults(
        cls,
        data: dict[str, Any],
        defaults: dict[str, Any],
    ) -> bool:
        """
        將缺少的預設欄位遞迴加入 Settings。

        已存在的值不會被預設值覆蓋。
        回傳是否有修改 Settings。
        """

        changed = False

        for key, default_value in defaults.items():
            if key not in data:
                data[key] = copy.deepcopy(default_value)
                changed = True
                continue

            current_value = data[key]

            if (
                isinstance(current_value, dict)
                and isinstance(default_value, dict)
            ):
                if cls._merge_defaults(
                    current_value,
                    default_value,
                ):
                    changed = True

        return changed

    # ── Schema 驗證 ──────────────────────

    @classmethod
    def _validate_default_types(
        cls,
        data: dict[str, Any],
        defaults: dict[str, Any],
        prefix: str,
    ) -> None:
        """依預設值遞迴驗證既有欄位的基本型別。"""

        for key, default_value in defaults.items():
            if key not in data:
                continue

            value = data[key]
            path = f"{prefix}.{key}"

            if isinstance(default_value, dict):
                if not isinstance(value, dict):
                    raise ValueError(f"{path} 必須是 JSON Object")
                cls._validate_default_types(value, default_value, path)
                continue

            if default_value is None:
                continue

            expected = type(default_value)
            if expected is int and isinstance(value, bool):
                raise ValueError(f"{path} 必須是 int")
            if not isinstance(value, expected):
                raise ValueError(f"{path} 必須是 {expected.__name__}")

    def _validate(self, name: str, data: dict[str, Any]) -> None:
        """驗證指定 Settings 的基本型別與額外 Schema。"""

        defaults = self._defaults.get(name)
        if defaults is not None:
            self._validate_default_types(data, defaults, name)

        for relative_path, rule in self._schemas.get(name, {}).items():
            current: Any = data
            for part in relative_path.split("."):
                if not isinstance(current, dict) or part not in current:
                    raise ValueError(f"{name}.{relative_path} 缺少必要欄位")
                current = current[part]
            rule.validate(f"{name}.{relative_path}", current)

    # ── Module 註冊 ──────────────────────

    def register(
        self,
        name: str,
        defaults: dict[str, Any],
        schema: dict[str, SettingRule] | None = None,
    ) -> dict[str, Any]:
        """
        註冊 Settings 與其預設值。

        設定檔不存在時自動建立。
        設定檔存在時只補上缺少的預設欄位。
        """

        self._defaults[name] = copy.deepcopy(defaults)
        self._schemas[name] = dict(schema or {})

        path = self._get_path(name)

        if not path.exists():
            data = copy.deepcopy(defaults)

            self._settings[name] = data
            self.save(name)

            return data

        data = self.load(name)

        if self._merge_defaults(
            data,
            defaults,
        ):
            self.save(name)

        self._validate(name, data)
        return data

    # ── 載入 ──────────────────────

    def load(
        self,
        name: str,
    ) -> dict[str, Any]:
        """載入指定 Settings 檔案。"""

        path = self._get_path(name)

        if not path.exists():
            defaults = self._defaults.get(name)

            if defaults is None:
                self._settings[name] = {}
                return {}

            data = copy.deepcopy(defaults)

            self._settings[name] = data
            self.save(name)

            return data

        try:
            with path.open(
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(file)

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Settings 格式錯誤：{path}"
            ) from exc

        except OSError as exc:
            raise RuntimeError(
                f"Settings 讀取失敗：{path}"
            ) from exc

        if not isinstance(data, dict):
            raise RuntimeError(
                f"Settings 根節點必須是 JSON Object：{path}"
            )

        defaults = self._defaults.get(name)

        changed = False

        if defaults is not None:
            changed = self._merge_defaults(
                data,
                defaults,
            )

        try:
            self._validate(name, data)
        except ValueError as exc:
            raise RuntimeError(f"Settings 驗證失敗：{path}: {exc}") from exc

        existing = self._settings.get(name)
        if existing is not None:
            existing.clear()
            existing.update(data)
            data = existing
        else:
            self._settings[name] = data

        if changed:
            self.save(name)

        return data

    def load_all(self) -> None:
        """載入 settings/ 內所有 JSON 設定檔。"""

        if not self.settings_dir.exists():
            return

        for path in sorted(
            self.settings_dir.glob("*.json")
        ):
            self.load(path.stem)

    # ── 儲存 ──────────────────────

    def save(
        self,
        name: str,
    ) -> None:
        """將指定 Settings 儲存至 JSON。"""

        data = self._settings.get(name)

        if data is None:
            raise KeyError(
                f"Settings 尚未載入：{name}"
            )

        path = self._get_path(name)

        try:
            self.settings_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{name}-",
                suffix=".tmp",
                dir=self.settings_dir,
                text=True,
            )

            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                    json.dump(
                        data,
                        file,
                        ensure_ascii=False,
                        indent=2,
                    )

                    file.write("\n")
                    file.flush()
                    os.fsync(file.fileno())

                os.replace(temporary_name, path)
            finally:
                Path(temporary_name).unlink(missing_ok=True)

        except OSError as exc:
            raise RuntimeError(
                f"Settings 儲存失敗：{path}"
            ) from exc

    # ── 修改 ──────────────────────

    def set(
        self,
        path: str,
        value: Any,
        *,
        save: bool = True,
    ) -> None:
        """
        以「檔名.欄位.子欄位」格式修改設定。

        Example:
            set(
                "logging.error_reporting.enabled",
                False,
            )
        """

        parts = path.split(".")

        if len(parts) < 2:
            raise ValueError(
                "Settings 路徑至少需要包含檔名與欄位"
            )

        settings_name = parts[0]

        if settings_name not in self._settings:
            self.load(settings_name)

        data = self._settings[settings_name]
        target = data

        for key in parts[1:-1]:
            current = target.get(key)

            if current is None:
                target[key] = {}
                current = target[key]

            if not isinstance(current, dict):
                raise ValueError(
                    f"Settings 路徑不是 Object："
                    f"{'.'.join(parts[:-1])}"
                )

            target = current

        key = parts[-1]
        had_old_value = key in target
        old_value = target.get(key)
        target[key] = value

        try:
            self._validate(settings_name, data)
        except ValueError:
            if had_old_value:
                target[key] = old_value
            else:
                target.pop(key, None)
            raise

        if save:
            self.save(settings_name)

    # ── 重新載入 ──────────────────────

    def reload(
        self,
        name: str,
    ) -> dict[str, Any]:
        """重新載入指定 Settings。"""

        return self.load(name)

    def reload_all(self) -> None:
        """重新載入全部已存在與已註冊 Settings。"""

        names = set(self._settings)
        names.update(self._defaults)

        if self.settings_dir.exists():
            names.update(
                path.stem
                for path in self.settings_dir.glob("*.json")
            )

        self._settings.clear()

        for name in sorted(names):
            self.load(name)

    # ── 查詢 ──────────────────────

    def get(
        self,
        path: str,
        default: Any = None,
    ) -> Any:
        """
        以「檔名.欄位.子欄位」格式取得設定。

        Example:
            get("bot.command_prefix", "$")
            get("bot.presence.status", "online")
        """

        parts = path.split(".")

        if len(parts) < 2:
            return default

        settings_name = parts[0]

        if settings_name not in self._settings:
            self.load(settings_name)

        value: Any = self._settings.get(
            settings_name,
            {},
        )

        for key in parts[1:]:
            if not isinstance(value, dict):
                return default

            if key not in value:
                return default

            value = value[key]

        return value


# ── 全域 Settings ──────────────────────

settings = SettingsManager()


def get(
    path: str,
    default: Any = None,
) -> Any:
    """從全域 Settings Manager 取得設定。"""

    return settings.get(
        path,
        default,
    )


def set_value(
    path: str,
    value: Any,
    *,
    save: bool = True,
) -> None:
    """透過全域 Settings Manager 修改設定。"""

    settings.set(
        path,
        value,
        save=save,
    )
