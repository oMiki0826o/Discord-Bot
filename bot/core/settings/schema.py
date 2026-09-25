"""
bot/core/settings/schema.py

Modification():

- 定義 Settings 欄位驗證規則。
- 提供型別、範圍、允許值與自訂驗證。
- 產生一致且可讀的設定錯誤訊息。

本檔只負責描述與驗證單一 Settings 欄位規則。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


# ── Schema Rule ──────────────────────

@dataclass(frozen=True, slots=True)
class SettingRule:
    """描述單一 Settings 欄位的額外驗證條件。"""

    expected_type: type | tuple[type, ...] | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    choices: frozenset[Any] | None = None
    allow_none: bool = False
    validator: Callable[[Any], bool] | None = None
    description: str = ""

    def validate(self, path: str, value: Any) -> None:
        """驗證值；不符合規則時拋出 ValueError。"""

        if value is None:
            if self.allow_none:
                return
            raise ValueError(f"{path} 不可為 null")

        if self.expected_type is not None and not _matches_type(value, self.expected_type):
            raise ValueError(f"{path} 型別錯誤，收到 {type(value).__name__}")

        if self.minimum is not None and value < self.minimum:
            raise ValueError(f"{path} 不可小於 {self.minimum}")

        if self.maximum is not None and value > self.maximum:
            raise ValueError(f"{path} 不可大於 {self.maximum}")

        if self.choices is not None and value not in self.choices:
            choices = ", ".join(sorted(map(str, self.choices)))
            raise ValueError(f"{path} 必須是以下值之一：{choices}")

        if self.validator is not None and not self.validator(value):
            suffix = f"：{self.description}" if self.description else ""
            raise ValueError(f"{path} 不符合設定限制{suffix}")


def _matches_type(value: Any, expected: type | tuple[type, ...]) -> bool:
    """嚴格判斷設定型別，避免 bool 被視為 int。"""

    expected_types = expected if isinstance(expected, tuple) else (expected,)
    if bool not in expected_types and isinstance(value, bool):
        return False
    return isinstance(value, expected_types)
