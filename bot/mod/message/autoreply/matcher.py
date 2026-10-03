"""
bot/mod/message/autoreply/matcher.py

Modification():

- Priority matcher with regex timeout and per-rule cooldowns。
"""

from __future__ import annotations

from dataclasses import dataclass

import regex

from bot.core.logging.manager import LogManager
from bot.mod.message.autoreply.model import AutoReplyDocument, AutoReplyRule, MatchMode


logger = LogManager().get_logger("message.autoreply.matcher")


@dataclass(frozen=True, slots=True)
class MatchInput:
    guild_id: int
    channel_id: int
    user_id: int
    content: str
    user_name: str
    user_mention: str
    channel_mention: str
    guild_name: str


@dataclass(frozen=True, slots=True)
class AutoReplyMatch:
    rule_id: str
    rendered_response: str


class AutoReplyMatcher:
    def __init__(self, *, regex_timeout_seconds: float) -> None:
        self.regex_timeout_seconds = regex_timeout_seconds
        self._cooldowns: dict[tuple[int, str, int, int], float] = {}

    def _matches(self, rule: AutoReplyRule, content: str) -> tuple[bool, str]:
        candidate = content if rule.case_sensitive else content.casefold()
        pattern = rule.pattern if rule.case_sensitive else rule.pattern.casefold()
        if rule.mode is MatchMode.EXACT:
            return candidate == pattern, content
        if rule.mode is MatchMode.CONTAINS:
            return pattern in candidate, rule.pattern
        flags = 0 if rule.case_sensitive else regex.IGNORECASE | regex.FULLCASE
        try:
            found = regex.search(
                rule.pattern,
                content,
                flags=flags,
                timeout=self.regex_timeout_seconds,
            )
        except (regex.error, TimeoutError) as exc:
            logger.warning("自動回覆 regex 略過 rule=%s error=%s", rule.id, exc)
            return False, ""
        return found is not None, found.group(0) if found else ""

    def find(
        self,
        document: AutoReplyDocument,
        value: MatchInput,
        *,
        now: float,
        consume_cooldown: bool = True,
    ) -> AutoReplyMatch | None:
        for rule in sorted(document.rules, key=lambda item: (-item.priority, item.id)):
            if not rule.enabled:
                continue
            if rule.allowed_channel_ids and value.channel_id not in rule.allowed_channel_ids:
                continue
            if value.channel_id in rule.blocked_channel_ids:
                continue
            key = (value.guild_id, rule.id, value.channel_id, value.user_id)
            matched, match_text = self._matches(rule, value.content)
            if not matched:
                continue
            # A higher-priority matching rule owns the message even while it is
            # cooling down; falling through would unexpectedly trigger a lower
            # priority response for the same text.
            if self._cooldowns.get(key, 0.0) > now:
                return None
            rendered = rule.response.format(
                user=value.user_mention,
                username=value.user_name,
                channel=value.channel_mention,
                guild=value.guild_name,
                match=match_text,
            )
            if consume_cooldown and rule.cooldown_seconds:
                self._cooldowns[key] = now + rule.cooldown_seconds
            return AutoReplyMatch(rule.id, rendered)
        if len(self._cooldowns) > 10_000:
            self._cooldowns = {key: expiry for key, expiry in self._cooldowns.items() if expiry > now}
        return None
