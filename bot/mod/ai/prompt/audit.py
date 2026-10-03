"""
bot/mod/ai/prompt/audit.py

Modification():

- Redact AI prompt diagnostics before an owner views them。
"""

from __future__ import annotations

import re

_SECRET = re.compile(r"(?i)((?:api[_ -]?key|token|password|authorization)\s*[:=]\s*)\S+")
_BLOCKS = (
    ("Attachment", "[attachment content omitted]"),
    ("Channel context", "[channel context omitted]"),
    ("Global memory", "[memory content omitted]"),
)


def redact_prompt(text: str) -> str:
    """Return a content-safe diagnostic representation of a prompt."""

    redacted = _SECRET.sub(r"\1[redacted]", text)
    for marker, replacement in _BLOCKS:
        redacted = re.sub(rf"{re.escape(marker)}.*?(?=\n[A-Z][^\n]*:|\Z)", replacement, redacted, flags=re.DOTALL)
    return redacted


def render_prompt_audit(request_id: str, user_id: str, text: str) -> str:
    """Render a bounded, redacted owner diagnostic without request content leaks."""

    return f"AI prompt audit | request={request_id} user={user_id}\n{redact_prompt(text)}"
