"""
bot/core/discord/help/builder.py

Modification():

- Build paginated, user-facing command help from registered modules。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .models import HelpCategory, HelpEntry, HelpPage


def module_display_name(bot: Any, module_name: str) -> str:
    if module_name == "other":
        return "其他"
    registry = getattr(getattr(bot, "module_loader", None), "registry", None)
    module = None if registry is None else registry.get(module_name)
    return module.display_name if module is not None else module_name.replace("_", " ").title()


def build_help_categories(
    commands_by_category: dict[str, list[HelpEntry]],
    *,
    category_name_resolver: Callable[[str], str] | None = None,
    entries_per_page: int = 6,
) -> tuple[HelpCategory, ...]:
    if entries_per_page < 1:
        raise ValueError("entries_per_page must be at least 1")
    resolver = category_name_resolver or (lambda name: name.replace("_", " ").title())
    categories: list[HelpCategory] = []
    for name in sorted(commands_by_category):
        entries = sorted(commands_by_category[name], key=lambda entry: entry.name)
        pages = tuple(HelpPage(name, tuple(entries[index:index + entries_per_page])) for index in range(0, len(entries), entries_per_page))
        if pages:
            categories.append(HelpCategory(resolver(name), pages))
    return tuple(categories)
