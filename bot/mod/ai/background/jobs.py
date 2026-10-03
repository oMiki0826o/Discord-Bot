"""
bot/mod/ai/background/jobs.py

Modification():

- 建立可於重啟後恢復的 Memory Job Repository。
- 實作有限次數與有上限的指數退避。

本檔案只處理 durable job state，不執行 Provider 請求。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from ..database import AiDatabase


class JobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class MemoryJob:
    job_id: str
    event_id: str
    status: JobStatus
    attempts: int
    available_at: int
    last_error: str
    created_at: int
    updated_at: int


class MemoryJobRepository:
    def __init__(self, database: AiDatabase, *, max_attempts: int, retry_base_seconds: int, retry_max_seconds: int) -> None:
        if min(max_attempts, retry_base_seconds, retry_max_seconds) < 1:
            raise ValueError("Memory job settings must be positive")
        self.database = database
        self.max_attempts = max_attempts
        self.retry_base_seconds = retry_base_seconds
        self.retry_max_seconds = retry_max_seconds

    def enqueue(self, event_id: str, *, now: int) -> MemoryJob:
        job_id = "memjob_" + hashlib.sha256(event_id.encode()).hexdigest()[:24]
        with self.database.transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO memory_jobs (job_id, event_id, status, attempts, available_at, created_at, updated_at) VALUES (?, ?, 'pending', 0, ?, ?, ?)",
                (job_id, event_id, now, now, now),
            )
            return self._get(connection, job_id)

    def recover_processing(self, *, now: int) -> int:
        with self.database.transaction() as connection:
            cursor = connection.execute("UPDATE memory_jobs SET status = 'pending', available_at = ?, updated_at = ? WHERE status = 'processing'", (now, now))
            return cursor.rowcount

    def claim(self, *, limit: int, now: int) -> tuple[MemoryJob, ...]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        with self.database.transaction() as connection:
            rows = connection.execute(
                "SELECT job_id FROM memory_jobs WHERE status = 'pending' AND available_at <= ? ORDER BY created_at, job_id LIMIT ?",
                (now, limit),
            ).fetchall()
            jobs: list[MemoryJob] = []
            for row in rows:
                connection.execute("UPDATE memory_jobs SET status = 'processing', attempts = attempts + 1, updated_at = ? WHERE job_id = ?", (now, row["job_id"]))
                jobs.append(self._get(connection, str(row["job_id"])))
            return tuple(jobs)

    def next_available_at(self) -> int | None:
        """回傳下一筆 pending job 的可執行時間。"""

        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT min(available_at) AS available_at "
                "FROM memory_jobs WHERE status = 'pending'"
            ).fetchone()
        if row is None or row["available_at"] is None:
            return None
        return int(row["available_at"])

    def complete(self, job_id: str, *, now: int) -> MemoryJob:
        with self.database.transaction() as connection:
            connection.execute("UPDATE memory_jobs SET status = 'completed', last_error = '', updated_at = ? WHERE job_id = ?", (now, job_id))
            return self._get(connection, job_id)

    def fail(self, job_id: str, error: str, *, now: int) -> MemoryJob:
        with self.database.transaction() as connection:
            current = self._get(connection, job_id)
            terminal = current.attempts >= self.max_attempts
            delay = min(self.retry_max_seconds, self.retry_base_seconds * (2 ** max(0, current.attempts - 1)))
            status = JobStatus.FAILED if terminal else JobStatus.PENDING
            available_at = now if terminal else now + delay
            connection.execute(
                "UPDATE memory_jobs SET status = ?, available_at = ?, last_error = ?, updated_at = ? WHERE job_id = ?",
                (status.value, available_at, error[:1000], now, job_id),
            )
            return self._get(connection, job_id)

    def reject(self, job_id: str, error: str, *, now: int) -> MemoryJob:
        """Finish a job whose model payload violates a deterministic contract.

        Retrying the exact same event cannot repair an invalid candidate shape;
        keep the reason for owner diagnostics without creating noisy retries.
        """

        with self.database.transaction() as connection:
            connection.execute(
                "UPDATE memory_jobs SET status = 'failed', available_at = ?, last_error = ?, updated_at = ? WHERE job_id = ?",
                (now, error[:1000], now, job_id),
            )
            return self._get(connection, job_id)

    def defer_quota(
        self,
        job_id: str,
        *,
        retry_after_seconds: int | None,
        now: int,
    ) -> MemoryJob:
        """Return a quota-limited job to pending without consuming an extraction attempt."""

        delay = self.retry_max_seconds if retry_after_seconds is None else max(1, retry_after_seconds)
        delay = min(self.retry_max_seconds, delay)
        with self.database.transaction() as connection:
            current = self._get(connection, job_id)
            attempts = max(0, current.attempts - 1)
            connection.execute(
                "UPDATE memory_jobs SET status = 'pending', attempts = ?, available_at = ?, last_error = ?, updated_at = ? WHERE job_id = ?",
                (attempts, now + delay, "provider_quota", now, job_id),
            )
            return self._get(connection, job_id)

    @staticmethod
    def _get(connection, job_id: str) -> MemoryJob:
        row = connection.execute("SELECT * FROM memory_jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise LookupError(f"Unknown memory job: {job_id}")
        return MemoryJob(str(row["job_id"]), str(row["event_id"]), JobStatus(str(row["status"])), int(row["attempts"]), int(row["available_at"]), str(row["last_error"]), int(row["created_at"]), int(row["updated_at"]))
