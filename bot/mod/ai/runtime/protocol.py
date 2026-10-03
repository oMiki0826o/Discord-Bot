"""
bot/mod/ai/runtime/protocol.py

Modification():

- 定義 AIService 對 active runtime 的最小依賴契約。
"""

from __future__ import annotations

from typing import Protocol

from .models import RuntimeRequest, RuntimeResult


class AiRuntime(Protocol):
    async def run(self, request: RuntimeRequest) -> RuntimeResult: ...

    async def close(self) -> None: ...
