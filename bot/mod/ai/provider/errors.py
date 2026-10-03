"""
bot/mod/ai/provider/errors.py

Modification():

- 建立供應商中立的錯誤分類。

本檔案讓上層不需依賴 Google SDK 例外類型。
"""

from __future__ import annotations


class ProviderError(RuntimeError):
    """AI Provider 錯誤基類別。"""


class ProviderQuotaError(ProviderError):
    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ProviderUnavailableError(ProviderError):
    """可在有限範圍內重試的供應商錯誤。"""


class ProviderTimeoutError(ProviderUnavailableError):
    """供應商逾時。"""


class ProviderEmptyResponseError(ProviderUnavailableError):
    """供應商沒有回傳可用文字。"""


class ProviderVerificationError(ProviderUnavailableError):
    """供應商未證實已成功完成要求的 grounding 或 URL Context。"""
