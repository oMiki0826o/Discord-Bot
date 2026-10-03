"""
bot/mod/ai/topics/repository.py

Modification():

- 以 optimistic version 寫入 Topic State 與 Evidence。
- 所有對外讀取都強制 user/scope 邊界。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence

from ..database import AiDatabase
from ..errors import TopicConflictError
from ..json_values import dump_json_value, normalize_json_value
from .models import (
    PutTopicState,
    TopicEvidence,
    TopicListQuery,
    TopicQuery,
    TopicScopeType,
    TopicState,
    TopicStatus,
)


class TopicRepository:
    def __init__(self, database: AiDatabase) -> None:
        self.database = database

    def put(
        self,
        command: PutTopicState,
        connection: sqlite3.Connection,
    ) -> TopicState:
        existing = self._get_scoped(connection, TopicQuery(
            topic_id=command.topic_id,
            user_id=command.user_id,
            scope_type=command.scope_type,
            scope_id=command.scope_id,
        ))
        if existing is None:
            collision = connection.execute(
                "SELECT 1 FROM topic_states WHERE topic_id = ?",
                (command.topic_id,),
            ).fetchone()
            if collision is not None:
                raise TopicConflictError("topic_id 已屬於其他 scope")
            if command.expected_version is not None:
                raise TopicConflictError("expected version 不適用於新 Topic")
            version = 1
            connection.execute(
                "INSERT INTO topic_states ("
                "topic_id, user_id, scope_type, scope_id, name, status, "
                "current_goal, state_json, version, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    command.topic_id, command.user_id, command.scope_type.value,
                    command.scope_id, command.name, command.status.value,
                    command.current_goal,
                    dump_json_value(command.state, field_name="state", max_bytes=20_000),
                    version, command.observed_at, command.observed_at,
                ),
            )
        else:
            if command.expected_version != existing.version:
                raise TopicConflictError("Topic version 已改變")
            if command.name != existing.name:
                raise TopicConflictError("Topic name 不得透過更新改變")
            if command.observed_at < existing.updated_at:
                raise TopicConflictError("older evidence cannot replace newer Topic State")
            version = existing.version + 1
            changed = connection.execute(
                "UPDATE topic_states SET status = ?, current_goal = ?, "
                "state_json = ?, version = ?, updated_at = ? "
                "WHERE topic_id = ? AND user_id = ? AND scope_type = ? "
                "AND scope_id = ? AND version = ?",
                (
                    command.status.value,
                    command.current_goal,
                    dump_json_value(command.state, field_name="state", max_bytes=20_000),
                    version,
                    command.observed_at,
                    command.topic_id,
                    command.user_id,
                    command.scope_type.value,
                    command.scope_id,
                    command.expected_version,
                ),
            ).rowcount
            if changed != 1:
                raise TopicConflictError("Topic version 已被並行更新")

        connection.execute(
            "INSERT INTO topic_evidence (topic_id, event_id, version, created_at) "
            "VALUES (?, ?, ?, ?)",
            (command.topic_id, command.evidence_event_id, version, command.observed_at),
        )
        result = self._get_scoped(connection, TopicQuery(
            topic_id=command.topic_id,
            user_id=command.user_id,
            scope_type=command.scope_type,
            scope_id=command.scope_id,
        ))
        if result is None:
            raise RuntimeError("Topic 寫入後無法讀回")
        return result

    def get(self, query: TopicQuery) -> TopicState | None:
        with self.database.connect() as connection:
            return self._get_scoped(connection, query)

    def list(self, query: TopicListQuery) -> tuple[TopicState, ...]:
        filters = ["user_id = ?", "scope_type = ?", "scope_id = ?"]
        parameters: list[object] = [query.user_id, query.scope_type.value, query.scope_id]
        if query.statuses:
            placeholders = ", ".join("?" for _ in query.statuses)
            filters.append(f"status IN ({placeholders})")
            parameters.extend(status.value for status in query.statuses)
        parameters.append(query.limit)
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM topic_states WHERE " + " AND ".join(filters)
                + " ORDER BY updated_at DESC, topic_id LIMIT ?",
                parameters,
            ).fetchall()
        return tuple(self._from_row(row) for row in rows)

    def evidence(self, query: TopicQuery) -> tuple[TopicEvidence, ...]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT te.* FROM topic_evidence AS te "
                "JOIN topic_states AS ts ON ts.topic_id = te.topic_id "
                "WHERE ts.topic_id = ? AND ts.user_id = ? "
                "AND ts.scope_type = ? AND ts.scope_id = ? "
                "ORDER BY te.version, te.created_at, te.event_id",
                (query.topic_id, query.user_id, query.scope_type.value, query.scope_id),
            ).fetchall()
        return tuple(TopicEvidence(
            topic_id=str(row["topic_id"]),
            event_id=str(row["event_id"]),
            version=int(row["version"]),
            created_at=int(row["created_at"]),
        ) for row in rows)

    @classmethod
    def _get_scoped(
        cls,
        connection: sqlite3.Connection,
        query: TopicQuery,
    ) -> TopicState | None:
        row = connection.execute(
            "SELECT * FROM topic_states WHERE topic_id = ? AND user_id = ? "
            "AND scope_type = ? AND scope_id = ?",
            (query.topic_id, query.user_id, query.scope_type.value, query.scope_id),
        ).fetchone()
        return None if row is None else cls._from_row(row)

    @staticmethod
    def _from_row(row: Sequence[object]) -> TopicState:
        state = normalize_json_value(json.loads(str(row["state_json"])), field_name="state")
        if not isinstance(state, dict):
            raise ValueError("stored Topic state 必須是 JSON Object")
        return TopicState(
            topic_id=str(row["topic_id"]),
            user_id=str(row["user_id"]),
            scope_type=TopicScopeType(str(row["scope_type"])),
            scope_id=str(row["scope_id"]),
            name=str(row["name"]),
            status=TopicStatus(str(row["status"])),
            current_goal=None if row["current_goal"] is None else str(row["current_goal"]),
            state=state,
            version=int(row["version"]),
            created_at=int(row["created_at"]),
            updated_at=int(row["updated_at"]),
        )
