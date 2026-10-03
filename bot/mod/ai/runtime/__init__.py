"""
bot/mod/ai/runtime/__init__.py

Modification():

- 匯出 AI-owned runtime 中立契約與基礎執行器。

本 package 不包含 Agent Tool Loop。
"""

from .basic import BasicRuntime
from .models import RuntimeRequest, RuntimeResult, RuntimeStopReason
from .protocol import AiRuntime

__all__ = (
    "AiRuntime",
    "BasicRuntime",
    "RuntimeRequest",
    "RuntimeResult",
    "RuntimeStopReason",
)
