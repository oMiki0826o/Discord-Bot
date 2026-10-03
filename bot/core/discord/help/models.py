"""
bot/core/discord/help/models.py

Modification():

- Immutable data structures shared by Slash and Prefix help。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class HelpEntry:
    name: str
    description: str


@dataclass(slots=True, frozen=True)
class HelpPage:
    category: str
    entries: tuple[HelpEntry, ...]


@dataclass(slots=True, frozen=True)
class HelpCategory:
    name: str
    pages: tuple[HelpPage, ...]
