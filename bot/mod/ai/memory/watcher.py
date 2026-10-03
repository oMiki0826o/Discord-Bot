"""
bot/mod/ai/memory/watcher.py

Modification():

- 以 asyncio 週期掃描 Owner Memory JSON。
- 以內容雜湊與連續兩次觀察做簡單防抖，避免讀取半寫入檔案。
- 忽略 MemoryMirrorService 自己的原子寫入，避免同步迴圈。
- 監測檔案刪除並交由 Mirror 轉為可稽核的 Owner 撤銷。
- 單一檔案失敗只記錄狀態，不終止 Watcher Task。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
import time
from typing import Any

logger = logging.getLogger(__name__)


class MemoryMirrorWatcher:
    """Poll-based Owner Memory Mirror watcher。"""

    def __init__(
        self,
        mirror: Any,
        root: Path,
        interval: float = 2.0,
    ) -> None:
        if interval <= 0:
            raise ValueError("Memory Mirror scan interval 必須大於 0")
        self.mirror = mirror
        self.root = Path(root)
        self.interval = float(interval)
        self._task: asyncio.Task[None] | None = None
        self._applied_hashes: dict[Path, str] = {}
        self._pending_hashes: dict[Path, tuple[str, int]] = {}
        self._missing_counts: dict[Path, int] = {}
        self._tracked_paths: set[Path] = set()
        self.last_scan_at: int | None = None
        self.last_error: str = ""
        self.error_count = 0
        self.applied_changes = 0

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return

    async def _run(self) -> None:
        while True:
            try:
                await self.scan_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.error_count += 1
                self.last_error = "watcher scan failed"
                logger.exception("Memory mirror scan failed")
            await asyncio.sleep(self.interval)

    async def scan_once(self) -> int:
        """掃描一次；只有完成套用的 Owner 變更才計入回傳值。"""

        self.last_scan_at = int(time.time())
        changed = 0
        current_paths = {
            path
            for path in self.root.glob("*.json")
            if path.is_file()
        } if self.root.is_dir() else set()

        for path in sorted(current_paths):
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError as exc:
                self._record_error(path, exc)
                continue

            self._tracked_paths.add(path)
            self._missing_counts.pop(path, None)

            if self.mirror.consume_written_hash(path, digest):
                self._applied_hashes[path] = digest
                self._pending_hashes.pop(path, None)
                continue
            if self._applied_hashes.get(path) == digest:
                self._pending_hashes.pop(path, None)
                continue

            pending_digest, count = self._pending_hashes.get(path, ("", 0))
            if pending_digest != digest:
                self._pending_hashes[path] = (digest, 1)
                continue
            if count < 1:
                self._pending_hashes[path] = (digest, count + 1)
                continue

            try:
                report = self.mirror.apply_path(path)
            except Exception as exc:
                # Do not retry the same invalid bytes every interval. A content
                # change produces a new digest and therefore a new attempt.
                self._applied_hashes[path] = digest
                self._pending_hashes.pop(path, None)
                self._record_error(path, exc)
                continue

            final_digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.mirror.consume_written_hash(path, final_digest)
            self._applied_hashes[path] = final_digest
            self._pending_hashes.pop(path, None)
            changed += report.changed

        # A deleted mirror gets the same two-scan debounce before it retracts
        # all active memories for that user.
        for path in sorted(self._tracked_paths - current_paths):
            count = self._missing_counts.get(path, 0) + 1
            self._missing_counts[path] = count
            if count < 2:
                continue
            try:
                report = self.mirror.apply_deleted_path(path)
            except Exception as exc:
                self._record_error(path, exc)
            else:
                changed += report.changed
            self._tracked_paths.discard(path)
            self._applied_hashes.pop(path, None)
            self._pending_hashes.pop(path, None)
            self._missing_counts.pop(path, None)

        self.applied_changes += changed
        return changed

    def snapshot(self) -> dict[str, int | str | None]:
        return {
            "last_scan_at": self.last_scan_at,
            "last_error": self.last_error,
            "error_count": self.error_count,
            "applied_changes": self.applied_changes,
            "tracked_files": len(self._tracked_paths),
        }

    def _record_error(self, path: Path, exc: Exception) -> None:
        self.error_count += 1
        self.last_error = f"{path.name}: {type(exc).__name__}: {exc}"[:500]
        logger.warning(
            "Memory mirror ignored %s: %s",
            path.name,
            exc,
        )
