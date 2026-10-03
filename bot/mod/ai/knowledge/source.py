"""
bot/mod/ai/knowledge/source.py

Modification():

Knowledge 原稿讀取邊界。

`data/ai/knowledge/` 中的文字檔是正式內容；SQLite 的 chunk、FTS 與向量
只用來找候選結果。此類別集中處理安全路徑解析，讓檢索結果必須回到原稿驗證。
"""

from __future__ import annotations

from pathlib import Path

from .service import KnowledgeDocument

KNOWLEDGE_SOURCE_SUFFIXES = frozenset({
    ".md", ".txt", ".java", ".py", ".js", ".ts", ".json", ".yaml", ".yml",
    ".toml", ".xml", ".gradle", ".properties", ".sql", ".sh",
    ".mcfunction",
})


class KnowledgeSourceReader:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def read(self, source_id: str) -> KnowledgeDocument:
        path = self._resolve(source_id)
        return KnowledgeDocument(
            source_id=source_id,
            title=path.stem,
            content=path.read_text(encoding="utf-8"),
            origin=source_id,
        )

    def _resolve(self, source_id: str) -> Path:
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_id must not be blank")
        relative = Path(source_id)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("source_id must be a relative path")
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("knowledge source escapes its root")
        if path.suffix.casefold() not in KNOWLEDGE_SOURCE_SUFFIXES:
            raise ValueError("unsupported knowledge file type")
        if not path.is_file():
            raise FileNotFoundError(source_id)
        return path
