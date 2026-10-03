"""
bot/mod/ai/data_sync.py

Modification():

- Safe, owner-facing validation for editable AI data sources。
"""

from __future__ import annotations

import json
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .memory.manual_sync import ManualMemorySyncService
from .errors import PromptSourceError
from .prompt.loader import PromptSourceLoader


@dataclass(frozen=True, slots=True)
class OwnerDataReport:
    valid: bool
    manual_records: int
    knowledge_documents: int
    changed_sources: int = 0
    removed_sources: int = 0
    issues: tuple[str, ...] = ()


class OwnerDataService:
    """Validate editable data without mutating source files or SQLite."""

    def __init__(
        self,
        root: Path,
        *,
        manual_memory: ManualMemorySyncService,
        prompts: PromptSourceLoader,
        max_source_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        if max_source_bytes < 1:
            raise ValueError("max_source_bytes must be positive")
        self.root = Path(root)
        self.manual_memory = manual_memory
        self.prompts = prompts
        self.max_source_bytes = max_source_bytes

    def validate(self) -> OwnerDataReport:
        issues = self._scan_sources()
        records = 0
        try:
            records = self.manual_memory.validate().records
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            issues.append(f"users_memory: {exc}")
        issues.extend(self._validate_prompt_json())
        try:
            self.prompts.load()
        except (ValueError, PromptSourceError) as exc:
            issues.append(f"prompt: {exc}")
        changed, removed = self._manifest_diff()
        return OwnerDataReport(
            valid=not issues,
            manual_records=records,
            knowledge_documents=self._knowledge_documents(),
            changed_sources=changed,
            removed_sources=removed,
            issues=tuple(issues),
        )

    def preview(self) -> OwnerDataReport:
        """Preview has exactly the same no-write validation contract."""
        return self.validate()

    def mark_applied(self) -> None:
        """Store the validated source snapshot only after a successful sync."""

        sources = self._source_manifest()
        with self.manual_memory.database.transaction() as connection:
            connection.execute("DELETE FROM ai_data_manifest")
            connection.executemany(
                "INSERT INTO ai_data_manifest (source_path, content_hash, source_type, applied_at) VALUES (?, ?, ?, ?)",
                [
                    (path, content_hash, source_type, int(time.time()))
                    for path, (content_hash, source_type) in sources.items()
                ],
            )

    def _scan_sources(self) -> list[str]:
        issues: list[str] = []
        if not self.root.exists():
            return [f"data root does not exist: {self.root}"]
        root = self.root.resolve()
        for path in sorted(self.root.rglob("*")):
            if path.is_dir():
                continue
            relative = path.relative_to(self.root).as_posix()
            if path.is_symlink():
                issues.append(f"{relative}: symbolic links are not allowed")
                continue
            try:
                path.resolve(strict=True).relative_to(root)
                size = path.stat().st_size
            except OSError as exc:
                issues.append(f"{relative}: cannot read source ({exc})")
                continue
            if size > self.max_source_bytes:
                issues.append(f"{relative}: exceeds {self.max_source_bytes} bytes")
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                issues.append(f"{relative}: must be UTF-8")
            except OSError as exc:
                issues.append(f"{relative}: cannot read source ({exc})")
            else:
                if relative.startswith("knowledge/") and path.suffix.casefold() in {".md", ".txt"} and path.name != "填寫說明.md" and not text.strip():
                    issues.append(f"{relative}: knowledge document must not be blank")
        return issues

    def _validate_prompt_json(self) -> list[str]:
        issues: list[str] = []
        for name in ("keywords.json", "blocked_words.json", "memory.json"):
            path = self.root / "prompt" / name
            if not path.is_file():
                continue
            try:
                value: Any = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(value, (list, dict)):
                    raise ValueError("must be a JSON array or object")
                self.prompts._read_json_strings(name)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                issues.append(f"prompt/{name}: {exc}")
        return issues

    def _knowledge_documents(self) -> int:
        root = self.root / "knowledge"
        if not root.is_dir():
            return 0
        return sum(
            1 for path in root.rglob("*")
            if path.is_file() and not path.is_symlink()
            and path.suffix.casefold() in {".md", ".txt"}
            and path.name != "填寫說明.md"
        )

    def _source_manifest(self) -> dict[str, tuple[str, str]]:
        result: dict[str, tuple[str, str]] = {}
        if not self.root.is_dir():
            return result
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative = path.relative_to(self.root).as_posix()
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            if len(raw) > self.max_source_bytes:
                continue
            if relative.startswith("users_memory/"):
                source_type = "user_memory"
            elif relative.startswith("knowledge/"):
                source_type = "knowledge"
            elif relative.startswith("prompt/"):
                source_type = "prompt"
            else:
                continue
            result[relative] = (hashlib.sha256(raw).hexdigest(), source_type)
        return result

    def _manifest_diff(self) -> tuple[int, int]:
        current = self._source_manifest()
        with self.manual_memory.database.connect() as connection:
            previous = {
                str(row["source_path"]): (str(row["content_hash"]), str(row["source_type"]))
                for row in connection.execute("SELECT source_path, content_hash, source_type FROM ai_data_manifest")
            }
        changed = sum(1 for path, value in current.items() if previous.get(path) != value)
        removed = sum(1 for path in previous if path not in current)
        return changed, removed
