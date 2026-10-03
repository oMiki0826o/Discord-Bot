"""
bot/mod/agent/skills.py

Modification():

- 建立 Agent-owned Skill metadata 漸進列出與完整內容讀取。
- 限制 Skill 名稱，防止路徑穿越。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True, slots=True)
class SkillSummary:
    name: str
    summary: str
    when_to_use: str


@dataclass(frozen=True, slots=True)
class LoadedSkill:
    name: str
    content: str


class SkillService:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def list_skills(self) -> tuple[SkillSummary, ...]:
        if not self.root.is_dir():
            return ()
        summaries = []
        for path in sorted(self.root.glob("*/SKILL.md")):
            metadata, _body = self._parse(path.read_text(encoding="utf-8"))
            name = metadata.get("name", path.parent.name)
            if _SAFE_NAME.fullmatch(name):
                summaries.append(SkillSummary(name, metadata.get("summary", ""), metadata.get("when_to_use", "")))
        return tuple(summaries)

    def read_skill(self, name: str) -> LoadedSkill:
        if _SAFE_NAME.fullmatch(name) is None:
            raise ValueError("Invalid skill name")
        path = self.root / name / "SKILL.md"
        if not path.is_file():
            raise LookupError(f"Unknown skill: {name}")
        return LoadedSkill(name, path.read_text(encoding="utf-8"))

    @staticmethod
    def _parse(content: str) -> tuple[dict[str, str], str]:
        if not content.startswith("---\n") or "\n---\n" not in content[4:]:
            return {}, content
        header, body = content[4:].split("\n---\n", 1)
        metadata = {}
        for line in header.splitlines():
            key, separator, value = line.partition(":")
            if separator:
                metadata[key.strip()] = value.strip()
        return metadata, body
