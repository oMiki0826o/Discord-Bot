"""
bot/core/settings/migration.py

Modification():

- Versioned migrations for non-secret JSON settings documents。
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any


SettingsMigration = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class SettingsMigrationStatus:
    name: str
    current_version: int
    target_version: int
    pending_versions: tuple[int, ...]
    last_error: str = ""


def _read_version(name: str, data: dict[str, Any]) -> int:
    value = data.get("schema_version", 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise RuntimeError(f"Settings {name} 的 schema_version 必須是非負整數")
    return value


def version_only_migration(data: dict[str, Any]) -> dict[str, Any]:
    """Return a copy for releases that only introduce version tracking."""

    return copy.deepcopy(data)


def migrate_document(
    name: str,
    data: dict[str, Any],
    *,
    target_version: int,
    migrations: Mapping[int, SettingsMigration],
) -> tuple[dict[str, Any], tuple[int, ...]]:
    """Apply every pending migration to a copy of *data*."""

    if isinstance(target_version, bool) or target_version < 0:
        raise ValueError("target_version 必須是非負整數")
    current = _read_version(name, data)
    if current > target_version:
        raise RuntimeError(
            f"Settings {name} Schema v{current} 高於程式支援的 v{target_version}"
        )

    candidate = copy.deepcopy(data)
    applied: list[int] = []
    for version in range(current + 1, target_version + 1):
        migration = migrations.get(version)
        if migration is None:
            raise RuntimeError(f"Settings {name} 缺少 migration v{version}")
        try:
            result = migration(copy.deepcopy(candidate))
        except Exception as exc:
            raise RuntimeError(
                f"Settings {name} migration v{version} 執行失敗: {exc}"
            ) from exc
        if not isinstance(result, dict):
            raise RuntimeError(f"Settings {name} migration v{version} 必須回傳 dict")
        candidate = result
        candidate["schema_version"] = version
        applied.append(version)
    return candidate, tuple(applied)
