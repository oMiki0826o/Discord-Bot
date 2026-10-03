"""
bot/mod/ai/search/cache.py

Modification():

- Small in-memory cache for verified, successful search observations。
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any


@dataclass(frozen=True, slots=True)
class SearchObservation:
    text: str
    success: bool
    stable: bool = False


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    observation: SearchObservation
    expires_at: int


class SearchCache:
    """Cache exact and normalized query matches without caching failed provider output."""

    def __init__(
        self,
        *,
        short_ttl_seconds: int = 30 * 60,
        long_ttl_seconds: int = 24 * 60 * 60,
        fuzzy_threshold: float = 0.85,
        database: Any = None,
    ) -> None:
        if short_ttl_seconds < 1 or long_ttl_seconds < short_ttl_seconds or not 0.0 <= fuzzy_threshold <= 1.0:
            raise ValueError("invalid search cache TTL")
        self.short_ttl_seconds = short_ttl_seconds
        self.long_ttl_seconds = long_ttl_seconds
        self.fuzzy_threshold = fuzzy_threshold
        self.database = database
        self._entries: dict[str, _CacheEntry] = {}
        self._hits = 0
        self._misses = 0

    @staticmethod
    def normalize(query: str) -> str:
        return " ".join(query.casefold().split())

    def get(self, query: str, *, now: int) -> SearchObservation | None:
        key = self.normalize(query)
        entry = self._entries.get(key)
        if entry is not None and entry.expires_at > now:
            self._hits += 1
            return entry.observation
        if entry is not None:
            self._entries.pop(key, None)
        if self.database is not None:
            with self.database.transaction() as connection:
                connection.execute("DELETE FROM search_cache WHERE expires_at <= ?", (now,))
                rows = connection.execute(
                    "SELECT query, text, stable, expires_at FROM search_cache WHERE expires_at > ?", (now,),
                ).fetchall()
            for row in rows:
                observation = SearchObservation(str(row["text"]), True, bool(row["stable"]))
                cached = _CacheEntry(observation, int(row["expires_at"]))
                self._entries[str(row["query"])] = cached
                if str(row["query"]) == key or self._similar(key, str(row["query"])):
                    self._hits += 1
                    return observation
        for candidate, cached in self._entries.items():
            if cached.expires_at > now and self._similar(key, candidate):
                self._hits += 1
                return cached.observation
        self._misses += 1
        return None

    def put(self, query: str, observation: SearchObservation, *, now: int) -> None:
        key = self.normalize(query)
        if not key or not observation.success or not observation.text.strip():
            return
        ttl = self.long_ttl_seconds if observation.stable else self.short_ttl_seconds
        expires_at = now + ttl
        self._entries[key] = _CacheEntry(observation=observation, expires_at=expires_at)
        if self.database is not None:
            with self.database.transaction() as connection:
                connection.execute(
                    "INSERT INTO search_cache (query, text, stable, expires_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(query) DO UPDATE SET text=excluded.text, stable=excluded.stable, expires_at=excluded.expires_at",
                    (key, observation.text, int(observation.stable), expires_at),
                )

    def clear(self) -> None:
        self._entries.clear()
        if self.database is not None:
            with self.database.transaction() as connection:
                connection.execute("DELETE FROM search_cache")

    def status(self, *, now: int) -> dict[str, int]:
        expired = [key for key, entry in self._entries.items() if entry.expires_at <= now]
        for key in expired:
            self._entries.pop(key, None)
        if self.database is not None:
            with self.database.transaction() as connection:
                removed = connection.execute("DELETE FROM search_cache WHERE expires_at <= ?", (now,)).rowcount
                persisted = int(connection.execute("SELECT count(*) FROM search_cache").fetchone()[0])
            return {
                "entries": persisted,
                "expired": len(expired) + max(0, int(removed)),
                "hits": self._hits,
                "misses": self._misses,
            }
        return {
            "entries": len(self._entries),
            "expired": len(expired),
            "hits": self._hits,
            "misses": self._misses,
        }

    def _similar(self, query: str, candidate: str) -> bool:
        return SequenceMatcher(None, query, candidate).ratio() >= self.fuzzy_threshold
