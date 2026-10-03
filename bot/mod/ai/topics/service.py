"""
bot/mod/ai/topics/service.py

Modification():

- 驗證 Topic Evidence 的使用者、Scope、角色與時間。
- 提供 Topic State 的唯一對外 Facade。
"""

from __future__ import annotations

from ..database import AiDatabase
from ..errors import EvidenceNotFoundError, EvidenceScopeError
from ..history.models import EventRole
from ..history.repository import EventRepository
from .models import PutTopicState, TopicEvidence, TopicListQuery, TopicQuery, TopicScopeType, TopicState
from .repository import TopicRepository


class TopicService:
    def __init__(
        self,
        *,
        database: AiDatabase,
        event_repository: EventRepository,
        repository: TopicRepository | None = None,
    ) -> None:
        self.database = database
        self.event_repository = event_repository
        self.repository = repository or TopicRepository(database)

    def put(self, command: PutTopicState) -> TopicState:
        with self.database.transaction() as connection:
            event = self.event_repository._get_with_connection(
                connection,
                command.evidence_event_id,
            )
            if event is None:
                raise EvidenceNotFoundError(
                    f"找不到 Topic Evidence：{command.evidence_event_id}"
                )
            if event.role is not EventRole.USER:
                raise EvidenceScopeError("Topic Evidence 必須來自 user event")
            if event.user_id != command.user_id:
                raise EvidenceScopeError("Topic Evidence user_id 不一致")
            if (
                command.scope_type is TopicScopeType.CHANNEL
                and event.channel_id != command.scope_id
            ):
                raise EvidenceScopeError("Topic Evidence channel scope 不一致")
            if (
                command.scope_type is TopicScopeType.CONVERSATION
                and event.conversation_id != command.scope_id
            ):
                raise EvidenceScopeError("Topic Evidence conversation scope 不一致")
            if event.created_at != command.observed_at:
                raise EvidenceScopeError("Topic observed_at 必須對應 Evidence created_at")
            return self.repository.put(command, connection)

    def get(self, query: TopicQuery) -> TopicState | None:
        return self.repository.get(query)

    def list(self, query: TopicListQuery) -> tuple[TopicState, ...]:
        return self.repository.list(query)

    def evidence(self, query: TopicQuery) -> tuple[TopicEvidence, ...]:
        return self.repository.evidence(query)
