"""
bot/mod/guild/stats/model.py

Modification():

- Domain models for Guild statistic voice channels。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StatMetric(StrEnum):
    MEMBER_TOTAL = "member_total"
    HUMAN_TOTAL = "human_total"
    BOT_TOTAL = "bot_total"
    ONLINE_TOTAL = "online_total"
    ROLE_MEMBERS = "role_members"


@dataclass(frozen=True, slots=True)
class StatChannel:
    guild_id: int
    channel_id: int
    metric: StatMetric
    label_template: str
    role_id: int = 0
    enabled: bool = True
    last_rendered_name: str = ""
    last_error: str = ""

    def validate(self) -> None:
        if self.label_template.count("{count}") != 1:
            raise ValueError("label_template 必須包含一次 {count}")
        if len(self.label_template.format(count=0)) > 100:
            raise ValueError("統計頻道名稱不可超過 100 字")
        if self.metric is StatMetric.ROLE_MEMBERS and not self.role_id:
            raise ValueError("role_members 必須指定 role_id")
        if self.metric is not StatMetric.ROLE_MEMBERS and self.role_id:
            raise ValueError("只有 role_members 可以指定 role_id")
