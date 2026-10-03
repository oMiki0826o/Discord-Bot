"""bot/mod/ai/prompt/__init__.py

Modification():

- AI Module 的可替換 Prompt Source 與組裝邊界。。"""
from .composer import PromptComposer
from .loader import PromptSourceLoader
from .models import (
    PromptBundle,
    PromptContextBlock,
    PromptMessage,
    PromptRole,
    PromptSources,
)

__all__ = (
    "PromptBundle",
    "PromptComposer",
    "PromptContextBlock",
    "PromptMessage",
    "PromptRole",
    "PromptSourceLoader",
    "PromptSources",
)
