"""
bot/mod/guild/stats/repository.py

Modification():

- SQLite persistence for statistic voice-channel settings。
"""

from __future__ import annotations

from bot.mod.guild.database import GuildDatabase
from bot.mod.guild.stats.model import StatChannel, StatMetric


class GuildStatsRepository:
    def __init__(self, database: GuildDatabase) -> None:
        self.database = database

    def list_for_guild(self, guild_id: int) -> tuple[StatChannel, ...]:
        with self.database._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM guild_stat_channels WHERE guild_id = ? ORDER BY channel_id",
                (guild_id,),
            ).fetchall()
        return tuple(
            StatChannel(
                guild_id=int(row["guild_id"]), channel_id=int(row["channel_id"]),
                metric=StatMetric(row["metric"]), label_template=str(row["label_template"]),
                role_id=int(row["role_id"]), enabled=bool(row["enabled"]),
                last_rendered_name=str(row["last_rendered_name"]),
                last_error=str(row["last_error"]),
            )
            for row in rows
        )

    def upsert(self, value: StatChannel) -> None:
        value.validate()
        with self.database._connect() as connection:
            connection.execute(
                """
                INSERT INTO guild_stat_channels (
                    guild_id, channel_id, metric, label_template, role_id, enabled,
                    last_rendered_name, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, channel_id) DO UPDATE SET
                    metric=excluded.metric, label_template=excluded.label_template,
                    role_id=excluded.role_id, enabled=excluded.enabled,
                    last_rendered_name=excluded.last_rendered_name,
                    last_error=excluded.last_error, updated_at=CURRENT_TIMESTAMP
                """,
                (
                    value.guild_id, value.channel_id, value.metric.value,
                    value.label_template, value.role_id, int(value.enabled),
                    value.last_rendered_name, value.last_error,
                ),
            )

    def delete(self, guild_id: int, channel_id: int) -> None:
        with self.database._connect() as connection:
            connection.execute(
                "DELETE FROM guild_stat_channels WHERE guild_id = ? AND channel_id = ?",
                (guild_id, channel_id),
            )

    def update_result(
        self, guild_id: int, channel_id: int, *, name: str, error: str
    ) -> None:
        with self.database._connect() as connection:
            connection.execute(
                """UPDATE guild_stat_channels
                   SET last_rendered_name = ?, last_error = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE guild_id = ? AND channel_id = ?""",
                (name, error[:1000], guild_id, channel_id),
            )
