"""
bot/mod/ai/errors.py

Modification():

- 定義 AI Module 對外穩定的錯誤型別。

本檔不處理錯誤記錄或 Discord 呈現。
"""

from __future__ import annotations


class AiModuleError(RuntimeError):
    """AI Module 可識別的基礎錯誤。"""


class AiDatabaseBusyError(AiModuleError):
    """SQLite 暫時無法取得寫入鎖。"""


class EventConflictError(AiModuleError):
    """同一 Event 識別已對應到不同內容。"""


class CandidateConflictError(AiModuleError):
    """同一 Candidate 識別已對應到不同內容。"""


class CandidatePayloadError(AiModuleError):
    """Model Provider 回傳的 Candidate Payload 不符合契約。"""


class EvidenceNotFoundError(AiModuleError):
    """Memory Candidate 引用的原始 Event 不存在。"""


class EvidenceScopeError(AiModuleError):
    """Evidence 的角色、使用者或 Scope 與 Candidate 不一致。"""


class TopicConflictError(AiModuleError):
    """Topic 識別、時間或預期版本與目前狀態衝突。"""


class PromptSourceError(AiModuleError):
    """Prompt source 缺失、無法讀取或不符合內容限制。"""
