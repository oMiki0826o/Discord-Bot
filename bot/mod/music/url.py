"""
bot/mod/music/url.py

Modification():

- 驗證公開 YouTube 與 YouTube Music URL。

本檔提供 Music Module 共用的 URL 驗證功能。
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit


_HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def is_youtube_url(text: str) -> bool:
    """判斷文字是否為公開 YouTube 或 YouTube Music HTTP URL。"""
    cleaned = text.strip()
    if not _HTTP_URL_RE.match(cleaned):
        return False

    try:
        hostname = (urlsplit(cleaned).hostname or "").lower().rstrip(".")
    except ValueError:
        return False

    return (
        hostname == "youtu.be"
        or hostname == "youtube.com"
        or hostname.endswith(".youtube.com")
    )
