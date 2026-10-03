"""
bot/mod/ai/history/search.py

Modification():

- 提供強制 User/Channel Scope 的 History FTS5 查詢。
- 提供由 Event Store 重建可拋棄索引的入口。

History Search 不修改原始 Event。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..database import AiDatabase
from .lexical import normalize_lexical_query
from .models import EventRole, StoredEvent
from .repository import EventRepository


@dataclass(frozen=True, slots=True)
class HistorySearchQuery:
    user_id: str
    channel_id: str
    query: str
    conversation_id: str | None = None
    roles: tuple[EventRole, ...] = ()
    created_from: int | None = None
    created_to: int | None = None
    limit: int = 20

    def __post_init__(self) -> None:
        for name, value in (
            ("user_id", self.user_id),
            ("channel_id", self.channel_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} 不得空白")
        if self.conversation_id is not None and not self.conversation_id.strip():
            raise ValueError("conversation_id 不得空白")
        normalize_lexical_query(self.query)
        if any(not isinstance(role, EventRole) for role in self.roles):
            raise ValueError("roles 必須由 EventRole 組成")
        for name, value in (
            ("created_from", self.created_from),
            ("created_to", self.created_to),
        ):
            if value is not None and (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < 0
            ):
                raise ValueError(f"{name} 必須是非負整數")
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_from > self.created_to
        ):
            raise ValueError("created_from 不得晚於 created_to")
        if (
            not isinstance(self.limit, int)
            or isinstance(self.limit, bool)
            or not 1 <= self.limit <= 100
        ):
            raise ValueError("limit 必須介於 1 到 100")


@dataclass(frozen=True, slots=True)
class HistoryHit:
    event: StoredEvent
    score: float


class HistorySearchService:
    """以程式提供的 Scope 查詢 Event FTS 索引。"""

    def __init__(self, database: AiDatabase) -> None:
        self.database = database

    def search(
        self,
        query: HistorySearchQuery,
    ) -> tuple[HistoryHit, ...]:
        filters = [
            "event_search MATCH ?",
            "e.user_id = ?",
            "e.channel_id = ?",
        ]
        parameters: list[object] = [
            normalize_lexical_query(query.query),
            query.user_id,
            query.channel_id,
        ]
        if query.conversation_id is not None:
            filters.append("e.conversation_id = ?")
            parameters.append(query.conversation_id)
        if query.roles:
            placeholders = ", ".join("?" for _ in query.roles)
            filters.append(f"e.role IN ({placeholders})")
            parameters.extend(role.value for role in query.roles)
        if query.created_from is not None:
            filters.append("e.created_at >= ?")
            parameters.append(query.created_from)
        if query.created_to is not None:
            filters.append("e.created_at <= ?")
            parameters.append(query.created_to)
        parameters.append(query.limit)

        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT e.*, bm25(event_search) AS search_rank "
                "FROM event_search "
                "JOIN events AS e ON e.event_id = event_search.event_id "
                "WHERE " + " AND ".join(filters)
                + " ORDER BY search_rank, e.created_at DESC, e.event_id LIMIT ?",
                parameters,
            ).fetchall()

        return tuple(
            HistoryHit(
                event=EventRepository._from_row(row),
                score=-float(row["search_rank"]),
            )
            for row in rows
        )

    def rebuild(self) -> int:
        """從 immutable events 重建整個 FTS index。"""

        with self.database.transaction() as connection:
            connection.execute("DELETE FROM event_search")
            rows = connection.execute(
                "SELECT * FROM events ORDER BY created_at, event_id"
            ).fetchall()
            for row in rows:
                EventRepository._index_event(
                    connection,
                    EventRepository._from_row(row),
                )
            return len(rows)
