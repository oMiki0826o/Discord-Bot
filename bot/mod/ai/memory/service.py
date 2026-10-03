"""
bot/mod/ai/memory/service.py

Modification():

- 提供 P0 Memory Application 的單一對外入口。
- 驗證 Extractor 使用的是已保存且未被修改的原始 Event。
- 協調 Candidate Parsing、Consolidation 與 Active Memory Query。

本檔不呼叫 Provider、不建立 Background Task，也不組裝 Prompt。
"""

from __future__ import annotations

from ..database import AiDatabase
from ..errors import EventConflictError
from ..history.models import StoredEvent
from ..history.repository import EventRepository
from .consolidator import ConsolidationResult, MemoryConsolidator
from .extractor import MemoryCandidateParser
from .models import Memory, MemoryCandidate, MemoryQuery
from .policy import ConflictResolver
from .repository import MemoryRepository


# ── Memory Service ──────────────────────

class MemoryService:
    """封裝 P0 Memory Flow，避免上層直接操作 Repository。"""

    def __init__(
        self,
        *,
        database: AiDatabase,
        event_repository: EventRepository,
        memory_repository: MemoryRepository,
        resolver: ConflictResolver | None = None,
        parser: MemoryCandidateParser | None = None,
    ) -> None:
        self.event_repository = event_repository
        self.memory_repository = memory_repository
        self.parser = parser or MemoryCandidateParser()
        self.consolidator = MemoryConsolidator(
            database=database,
            repository=memory_repository,
            resolver=resolver or ConflictResolver(),
        )

    def process_extraction(
        self,
        event: StoredEvent,
        payload: object,
    ) -> tuple[ConsolidationResult, ...]:
        """解析並依序整併單一已保存 Event 的 Candidate。"""

        stored = self.event_repository.get(
            event.event_id
        )

        if stored is None:
            raise EventConflictError(
                "Extractor Event 尚未保存至 Event Store"
            )

        if stored != event:
            raise EventConflictError(
                "Extractor Event 與 Event Store 內容不一致"
            )

        candidates = self.parser.parse(
            stored,
            payload,
        )

        return tuple(
            self.consolidator.consolidate(candidate)
            for candidate in candidates
        )

    def consolidate(
        self,
        candidate: MemoryCandidate,
    ) -> ConsolidationResult:
        """整併已由可信任邊界建立的 Candidate。"""

        return self.consolidator.consolidate(
            candidate
        )

    def find_active(
        self,
        query: MemoryQuery,
    ) -> tuple[Memory, ...]:
        """取得明確 User/Scope 內的 Active Memory。"""

        return self.memory_repository.find_active(
            query
        )
