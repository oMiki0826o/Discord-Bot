"""
bot/mod/ai/attachments/document.py

Modification():

- 建立 PDF、DOCX、PPTX 與試算表的可選 MarkItDown parser。
- 使用安全臨時檔並在成功或失敗後移除。

本檔案只在解析文件時懶加載可選依賴。
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path


async def extract_document(filename: str, media_type: str, data: bytes) -> str:
    suffix = Path(filename).suffix
    descriptor, temporary_name = tempfile.mkstemp(suffix=suffix)
    path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        return await asyncio.to_thread(_convert, path)
    finally:
        path.unlink(missing_ok=True)


def _convert(path: Path) -> str:
    from markitdown import MarkItDown

    return (MarkItDown().convert(str(path)).text_content or "").strip()
