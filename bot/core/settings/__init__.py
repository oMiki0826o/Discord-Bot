"""
bot/core/settings/__init__.py

Modification():

- Public Settings schema and migration interfaces。
"""

from bot.core.settings.migration import (
    SettingsMigration,
    SettingsMigrationStatus,
    migrate_document,
    version_only_migration,
)

__all__ = (
    "SettingsMigration",
    "SettingsMigrationStatus",
    "migrate_document",
    "version_only_migration",
)
