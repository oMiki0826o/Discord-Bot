"""
bot/mod/ai/summary/repository.py

Modification():

- Persistence for validated, Event-derived conversation summaries。
"""

from __future__ import annotations

from dataclasses import dataclass

from ..database import AiDatabase


@dataclass(frozen=True, slots=True)
class ConversationSummary:
    conversation_id: str
    user_id: str
    first_event_id: str
    last_event_id: str
    source_hash: str
    content: str
    updated_at: int


class SummaryRepository:
    def __init__(self, database: AiDatabase) -> None:
        self.database = database

    def save(self, conversation_id: str, user_id: str, first_event_id: str, last_event_id: str, source_hash: str, content: str, *, now: int) -> ConversationSummary:
        if not all(item.strip() for item in (conversation_id, user_id, first_event_id, last_event_id, source_hash, content)):
            raise ValueError("summary fields must not be blank")
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT INTO conversation_summaries (conversation_id, user_id, first_event_id, last_event_id, source_hash, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(conversation_id) DO UPDATE SET user_id = excluded.user_id, first_event_id = excluded.first_event_id, last_event_id = excluded.last_event_id, source_hash = excluded.source_hash, content = excluded.content, updated_at = excluded.updated_at",
                (conversation_id, user_id, first_event_id, last_event_id, source_hash, content, now, now),
            )
        return ConversationSummary(conversation_id, user_id, first_event_id, last_event_id, source_hash, content, now)

    def current(self, conversation_id: str, user_id: str, first_event_id: str, last_event_id: str, source_hash: str) -> ConversationSummary | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM conversation_summaries WHERE conversation_id = ? AND user_id = ? AND first_event_id = ? AND last_event_id = ? AND source_hash = ?",
                (conversation_id, user_id, first_event_id, last_event_id, source_hash),
            ).fetchone()
        return None if row is None else ConversationSummary(str(row["conversation_id"]), str(row["user_id"]), str(row["first_event_id"]), str(row["last_event_id"]), str(row["source_hash"]), str(row["content"]), int(row["updated_at"]))
