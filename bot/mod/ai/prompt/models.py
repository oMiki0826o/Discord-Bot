"""
bot/mod/ai/prompt/models.py

Modification():

- 定義與 Provider SDK 無關的 Prompt Sources、Reference Blocks 與 Messages。
- 保持 system instruction、retrieved context 與 conversation 的角色邊界。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..context.models import ContextSource


class PromptRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class PromptSources:
    system: str
    persona: str
    background: str
    moderation_rules: str = ""
    keywords: tuple[str, ...] = ()
    blocked_words: tuple[str, ...] = ()
    global_memory: tuple[str, ...] = ()
    gemma_system: str = ""
    gemma_persona: str = ""
    gemma_background: str = ""

    def __post_init__(self) -> None:
        for name, value in (
            ("system", self.system),
            ("persona", self.persona),
            ("background", self.background),
        ):
            _require_content(name, value)
        if any(not isinstance(value, str) or not value.strip() for value in (*self.keywords, *self.blocked_words, *self.global_memory)):
            raise ValueError("prompt reference values 必須是非空字串")


@dataclass(frozen=True, slots=True)
class PromptMessage:
    role: PromptRole
    content: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, PromptRole):
            raise ValueError("role 必須是 PromptRole")
        _require_content("content", self.content)


@dataclass(frozen=True, slots=True)
class PromptContextBlock:
    item_id: str
    source: ContextSource
    content: str
    relevance: float
    importance: int
    confidence: float
    timestamp: int


@dataclass(frozen=True, slots=True)
class PromptBundle:
    system_instruction: str
    context_blocks: tuple[PromptContextBlock, ...]
    messages: tuple[PromptMessage, ...]
    context_used_tokens: int
    context_omitted_count: int


def _require_content(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 不得空白")
    if len(value) > 30_000:
        raise ValueError(f"{name} 不得超過 30000 字元")
