"""
bot/mod/ai/history/repository.py

Modification():

- 保存不可變更的 AI Event。
- 提供使用者、頻道與對話隔離的 History 查詢。

本檔只負責 Event Store 的 SQLite 存取，不進行內容推論。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence

from ..database import AiDatabase
from ..errors import EventConflictError
from .models import EventRole, EventScope, NewEvent, StoredEvent
from .lexical import normalize_lexical_document


# ── Event Repository ──────────────────────

class EventRepository:
    """提供 immutable Event 的儲存與範圍查詢。"""

    def __init__(
        self,
        database: AiDatabase,
    ) -> None:
        self.database = database

    def append(
        self,
        event: NewEvent,
    ) -> StoredEvent:
        """保存 Event；完全相同的重試視為成功。"""

        metadata_json = json.dumps(
            dict(event.metadata),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

        with self.database.transaction() as connection:
            existing = self._get_with_connection(
                connection,
                event.event_id,
            )

            if existing is not None:
                incoming = self._to_stored(event)
                if existing == incoming:
                    self._index_event(connection, existing)
                    return existing
                raise EventConflictError(
                    f"Event ID 已存在且內容不同：{event.event_id}"
                )

            try:
                connection.execute(
                    """
                    INSERT INTO events (
                        event_id,
                        user_id,
                        channel_id,
                        message_id,
                        conversation_id,
                        role,
                        content,
                        created_at,
                        metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.user_id,
                        event.channel_id,
                        event.message_id,
                        event.conversation_id,
                        event.role.value,
                        event.content,
                        event.created_at,
                        metadata_json,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise EventConflictError(
                    "Event 的 message_id 或識別資訊已被其他事件使用"
                ) from exc

            stored = self._get_with_connection(
                connection,
                event.event_id,
            )

            if stored is None:
                raise RuntimeError("Event 寫入後無法讀回")

            self._index_event(connection, stored)

            return stored

    def get(
        self,
        event_id: str,
    ) -> StoredEvent | None:
        """依 ID 取得 Event。"""

        if not isinstance(event_id, str) or not event_id.strip():
            raise ValueError("event_id 不得空白")

        with self.database.connect() as connection:
            return self._get_with_connection(
                connection,
                event_id,
            )

    def recent(
        self,
        scope: EventScope,
        *,
        limit: int = 20,
    ) -> tuple[StoredEvent, ...]:
        """取得 Scope 內由舊到新的 Event。"""

        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 200:
            raise ValueError("limit 必須介於 1 到 200")

        parameters: list[object] = [
            scope.user_id,
            scope.channel_id,
        ]
        conversation_filter = ""

        if scope.conversation_id is not None:
            conversation_filter = " AND conversation_id = ?"
            parameters.append(scope.conversation_id)

        parameters.append(limit)

        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM events
                WHERE user_id = ? AND channel_id = ?
                """
                + conversation_filter
                + " ORDER BY created_at DESC, event_id DESC LIMIT ?",
                parameters,
            ).fetchall()

        return tuple(
            self._from_row(row)
            for row in reversed(rows)
        )

    @classmethod
    def _get_with_connection(
        cls,
        connection: sqlite3.Connection,
        event_id: str,
    ) -> StoredEvent | None:
        row = connection.execute(
            "SELECT * FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        return None if row is None else cls._from_row(row)

    @staticmethod
    def _to_stored(
        event: NewEvent,
    ) -> StoredEvent:
        return StoredEvent(
            event_id=event.event_id,
            user_id=event.user_id,
            channel_id=event.channel_id,
            message_id=event.message_id,
            conversation_id=event.conversation_id,
            role=event.role,
            content=event.content,
            created_at=event.created_at,
            metadata=dict(event.metadata),
        )

    @staticmethod
    def _index_event(
        connection: sqlite3.Connection,
        event: StoredEvent,
    ) -> None:
        connection.execute(
            "DELETE FROM event_search WHERE event_id = ?",
            (event.event_id,),
        )
        connection.execute(
            "INSERT INTO event_search ("
            "event_id, user_id, channel_id, conversation_id, role, "
            "created_at, search_text) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event.event_id,
                event.user_id,
                event.channel_id,
                event.conversation_id,
                event.role.value,
                event.created_at,
                normalize_lexical_document(event.content),
            ),
        )

    @staticmethod
    def _from_row(
        row: Sequence[object],
    ) -> StoredEvent:
        return StoredEvent(
            event_id=str(row["event_id"]),
            user_id=str(row["user_id"]),
            channel_id=str(row["channel_id"]),
            message_id=(
                None
                if row["message_id"] is None
                else str(row["message_id"])
            ),
            conversation_id=str(row["conversation_id"]),
            role=EventRole(str(row["role"])),
            content=str(row["content"]),
            created_at=int(row["created_at"]),
            metadata=json.loads(str(row["metadata_json"])),
        )
