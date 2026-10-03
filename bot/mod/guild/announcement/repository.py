"""
bot/mod/guild/announcement/repository.py

Modification():

- Transactional SQLite repository for scheduled announcements。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

from bot.mod.guild.announcement.model import Announcement, AnnouncementStatus
from bot.mod.guild.database import GuildDatabase


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("時間必須包含時區")
    return value.astimezone(timezone.utc).isoformat()


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class AnnouncementRepository:
    def __init__(self, database: GuildDatabase) -> None:
        self.database = database

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Announcement:
        return Announcement(
            id=str(row["id"]), guild_id=int(row["guild_id"]),
            author_id=int(row["author_id"]), target_channel_id=int(row["target_channel_id"]),
            mention_role_id=int(row["mention_role_id"]), title=str(row["title"]),
            content=str(row["content"]), color=int(row["color"]),
            image_url=str(row["image_url"]), attachment_path=str(row["attachment_path"]),
            status=AnnouncementStatus(row["status"]), scheduled_at=_datetime(row["scheduled_at"]),
            claimed_at=_datetime(row["claimed_at"]), published_at=_datetime(row["published_at"]),
            discord_message_id=int(row["discord_message_id"]),
            failure_count=int(row["failure_count"]), last_error=str(row["last_error"]),
            created_at=_datetime(row["created_at"]), updated_at=_datetime(row["updated_at"]),
        )

    def create(self, value: Announcement) -> None:
        value.validate()
        with self.database._connect() as connection:
            connection.execute(
                """INSERT INTO guild_announcements (
                    id, guild_id, author_id, target_channel_id, mention_role_id,
                    title, content, color, image_url, attachment_path, status,
                    scheduled_at, claimed_at, published_at, discord_message_id,
                    failure_count, last_error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    value.id, value.guild_id, value.author_id, value.target_channel_id,
                    value.mention_role_id, value.title, value.content, value.color,
                    value.image_url, value.attachment_path, value.status.value,
                    _iso(value.scheduled_at), _iso(value.claimed_at), _iso(value.published_at),
                    value.discord_message_id, value.failure_count, value.last_error,
                    _iso(value.created_at), _iso(value.updated_at),
                ),
            )

    def get(self, guild_id: int, announcement_id: str) -> Announcement | None:
        with self.database._connect() as connection:
            row = connection.execute(
                "SELECT * FROM guild_announcements WHERE guild_id = ? AND id = ?",
                (guild_id, announcement_id),
            ).fetchone()
        return self._from_row(row) if row else None

    def list_history(self, guild_id: int, *, limit: int = 25) -> tuple[Announcement, ...]:
        with self.database._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM guild_announcements WHERE guild_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (guild_id, max(1, min(limit, 100))),
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def schedule(self, guild_id: int, announcement_id: str, when: datetime) -> None:
        now = datetime.now(timezone.utc)
        with self.database._connect() as connection:
            cursor = connection.execute(
                """UPDATE guild_announcements SET status = ?, scheduled_at = ?,
                   claimed_at = NULL, last_error = '', updated_at = ?
                   WHERE guild_id = ? AND id = ? AND status IN (?, ?)""",
                (
                    AnnouncementStatus.SCHEDULED.value, _iso(when), _iso(now), guild_id,
                    announcement_id, AnnouncementStatus.DRAFT.value, AnnouncementStatus.FAILED.value,
                ),
            )
        if cursor.rowcount != 1:
            raise ValueError("公告不存在或目前狀態不可排程")

    def cancel(self, guild_id: int, announcement_id: str) -> bool:
        with self.database._connect() as connection:
            cursor = connection.execute(
                """UPDATE guild_announcements SET status = ?, updated_at = ?
                   WHERE guild_id = ? AND id = ? AND status IN (?, ?)""",
                (
                    AnnouncementStatus.CANCELLED.value, _iso(datetime.now(timezone.utc)),
                    guild_id, announcement_id, AnnouncementStatus.DRAFT.value,
                    AnnouncementStatus.SCHEDULED.value,
                ),
            )
        return cursor.rowcount == 1

    def claim_due(
        self, *, now: datetime, stale_after: timedelta, limit: int
    ) -> tuple[Announcement, ...]:
        connection = self.database._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            stale = now - stale_after
            rows = connection.execute(
                """SELECT id FROM guild_announcements
                   WHERE (status = ? AND scheduled_at <= ?)
                      OR (status = ? AND claimed_at <= ?)
                   ORDER BY COALESCE(scheduled_at, claimed_at) LIMIT ?""",
                (
                    AnnouncementStatus.SCHEDULED.value, _iso(now),
                    AnnouncementStatus.PUBLISHING.value, _iso(stale), limit,
                ),
            ).fetchall()
            ids = [str(row["id"]) for row in rows]
            for announcement_id in ids:
                connection.execute(
                    "UPDATE guild_announcements SET status = ?, claimed_at = ?, updated_at = ? WHERE id = ?",
                    (AnnouncementStatus.PUBLISHING.value, _iso(now), _iso(now), announcement_id),
                )
            claimed = tuple(
                self._from_row(
                    connection.execute("SELECT * FROM guild_announcements WHERE id = ?", (item,)).fetchone()
                )
                for item in ids
            )
            connection.commit()
            return claimed
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def mark_published(
        self, guild_id: int, announcement_id: str, *, message_id: int, published_at: datetime
    ) -> None:
        with self.database._connect() as connection:
            connection.execute(
                """UPDATE guild_announcements SET status = ?, published_at = ?,
                   discord_message_id = ?, claimed_at = NULL, last_error = '', updated_at = ?
                   WHERE guild_id = ? AND id = ? AND status = ?""",
                (
                    AnnouncementStatus.PUBLISHED.value, _iso(published_at), message_id,
                    _iso(published_at), guild_id, announcement_id,
                    AnnouncementStatus.PUBLISHING.value,
                ),
            )

    def mark_failed(
        self, guild_id: int, announcement_id: str, *, error: str,
        retry_at: datetime | None,
    ) -> None:
        status = AnnouncementStatus.SCHEDULED if retry_at else AnnouncementStatus.FAILED
        now = datetime.now(timezone.utc)
        with self.database._connect() as connection:
            connection.execute(
                """UPDATE guild_announcements SET status = ?, scheduled_at = ?,
                   claimed_at = NULL, failure_count = failure_count + 1,
                   last_error = ?, updated_at = ?
                   WHERE guild_id = ? AND id = ? AND status = ?""",
                (
                    status.value, _iso(retry_at), error[:1000], _iso(now), guild_id,
                    announcement_id, AnnouncementStatus.PUBLISHING.value,
                ),
            )
