"""
bot/mod/ai/provider/quota.py

Modification():

- 建立模型級 429 cooldown 狀態。

本檔案只管理可拋棄的執行期配額狀態。
"""

from __future__ import annotations

import time
from collections.abc import Callable


class QuotaManager:
    def __init__(self, *, default_cooldown_seconds: int, clock: Callable[[], float] = time.monotonic) -> None:
        if default_cooldown_seconds < 0:
            raise ValueError("default_cooldown_seconds 不得小於 0")
        self.default_cooldown_seconds = default_cooldown_seconds
        self._clock = clock
        self._until: dict[str, float] = {}

    def remaining(self, model: str) -> float:
        return max(0.0, self._until.get(model, 0.0) - self._clock())

    def mark_exhausted(self, model: str, seconds: int | None = None) -> None:
        cooldown = self.default_cooldown_seconds if seconds is None else max(0, seconds)
        self._until[model] = self._clock() + cooldown

    def clear(self, model: str | None = None) -> None:
        if model is None:
            self._until.clear()
        else:
            self._until.pop(model, None)

    def snapshot(self) -> dict[str, float]:
        """Return remaining cooldown seconds by model, omitting ready models."""

        return {
            model: remaining
            for model in tuple(self._until)
            if (remaining := self.remaining(model)) > 0
        }
