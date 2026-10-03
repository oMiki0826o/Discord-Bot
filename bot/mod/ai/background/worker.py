"""
bot/mod/ai/background/worker.py

Modification():

- 建立可啟動、通知、回收的 durable Memory Worker。
- 使用 Event wake-up 而非固定間隔無限輪詢。

本檔案讓背景擷取失敗不影響前景回覆。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from ..provider.errors import ProviderQuotaError, ProviderUnavailableError
from ..errors import CandidatePayloadError

logger = logging.getLogger("bot.mod.ai.memory_worker")
Processor = Callable[[Any], Awaitable[None]]


class BackgroundMemoryWorker:
    def __init__(self, *, jobs: Any, events: Any, processor: Processor, batch_size: int, clock: Callable[[], int] = lambda: int(time.time())) -> None:
        self.jobs = jobs
        self.events = events
        self.processor = processor
        self.batch_size = batch_size
        self.clock = clock
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._timer: asyncio.TimerHandle | None = None
        self._closing = False

    def enqueue(self, event_id: str, *, now: int):
        job = self.jobs.enqueue(event_id, now=now)
        self._wake.set()
        return job

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._closing = False
        self.jobs.recover_processing(now=self.clock())
        self._task = asyncio.create_task(self._run(), name="ai-memory-worker")
        self._wake.set()

    async def run_once(self) -> int:
        completed = 0
        for job in self.jobs.claim(limit=self.batch_size, now=self.clock()):
            event = self.events.get(job.event_id)
            if event is None:
                self.jobs.fail(job.job_id, "event not found", now=self.clock())
                continue
            try:
                await self.processor(event)
            except ProviderQuotaError as exc:
                deferred = self.jobs.defer_quota(
                    job.job_id,
                    retry_after_seconds=exc.retry_after_seconds,
                    now=self.clock(),
                )
                logger.info(
                    "Memory job quota deferred job_id=%s available_at=%s",
                    deferred.job_id,
                    deferred.available_at,
                )
            except CandidatePayloadError as exc:
                rejected = self.jobs.reject(job.job_id, str(exc), now=self.clock())
                logger.warning(
                    "Memory job rejected invalid candidate job_id=%s reason=%s",
                    rejected.job_id,
                    rejected.last_error,
                )
            except ProviderUnavailableError as exc:
                retry = self.jobs.fail(job.job_id, str(exc), now=self.clock())
                logger.warning(
                    "Memory job provider unavailable; retry scheduled job_id=%s attempts=%d available_at=%s",
                    retry.job_id,
                    retry.attempts,
                    retry.available_at,
                )
            except Exception as exc:
                logger.exception("Memory job failed: %s", job.job_id)
                self.jobs.fail(job.job_id, str(exc), now=self.clock())
            else:
                self.jobs.complete(job.job_id, now=self.clock())
                completed += 1
        return completed

    async def _run(self) -> None:
        while not self._closing:
            await self._wake.wait()
            self._wake.clear()
            if self._closing:
                break
            await self.run_once()
            self._schedule_next()

    def _schedule_next(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        available_at = self.jobs.next_available_at()
        if available_at is None or self._closing:
            return
        delay = max(0.0, float(available_at - self.clock()))
        self._timer = asyncio.get_running_loop().call_later(delay, self._wake.set)

    async def close(self) -> None:
        """停止 Worker；進行中的 durable job 留待下次啟動 recover。"""

        self._closing = True
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        task = self._task
        self._task = None
        self._wake.set()
        if task is None:
            return
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return
