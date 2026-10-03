"""
bot/core/discord/natural_command.py

Modification():

- 提供全專案共用的自然語言指令格式。
- 統一處理自然語言指令的註冊、格式匹配與參數解析。
- 命中自然語言指令後執行對應 Handler，並回報訊息已由指令系統處理。
- Core 僅提供通用機制，不包含任何 Feature Module 的功能規則。

本檔負責自然語言指令的定義、註冊、解析與分派。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
import logging
import re

import discord


logger = logging.getLogger("bot.core.discord.natural_command")


# ── Types ──────────────────────

NaturalCommandHandler = Callable[
    [discord.Message, Mapping[str, str]],
    Awaitable[None],
]


# ── Command Definition ──────────────────────

@dataclass(frozen=True, slots=True)
class NaturalCommand:
    """
    定義一條自然語言指令。

    pattern:
        固定格式：
            "暫停"

        帶參數格式：
            "播放 {url}"
            "查詢 {query}"

    handler:
        命中後由對應 Feature Module 提供的執行函數。

    priority:
        數字越大越優先匹配。
    """

    pattern: str
    handler: NaturalCommandHandler
    priority: int = 0


@dataclass(frozen=True, slots=True)
class _CompiledCommand:
    owner: str
    command: NaturalCommand
    regex: re.Pattern[str]
    order: int


# ── Pattern Compiler ──────────────────────

_PARAMETER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _compile_pattern(pattern: str) -> re.Pattern[str]:
    """
    將：

        播放 {url}

    轉成可匹配：

        播放 https://example.com/...

    的完整正規表示式。
    """

    normalized = " ".join(pattern.strip().split())

    if not normalized:
        raise ValueError("Natural Command pattern 不可為空")

    parts: list[str] = []
    position = 0
    parameters: set[str] = set()

    for match in _PARAMETER_PATTERN.finditer(normalized):
        name = match.group(1)

        if name in parameters:
            raise ValueError(
                f"Natural Command 參數名稱重複: {name}"
            )

        parameters.add(name)

        literal = normalized[position:match.start()]
        parts.append(re.escape(literal))

        parts.append(
            rf"(?P<{name}>.+?)"
        )

        position = match.end()

    parts.append(
        re.escape(normalized[position:])
    )

    expression = "".join(parts)

    return re.compile(
        rf"^{expression}$",
        re.IGNORECASE,
    )


# ── Registry ──────────────────────

class NaturalCommandRegistry:
    """
    全專案共用的自然語言指令 Registry。

    Feature Module 只需要註冊：
        pattern
        handler
        priority

    Registry 負責：
        儲存
        排序
        匹配
        參數解析
        執行
        訊息攔截判定
    """

    def __init__(self) -> None:
        self._commands: list[_CompiledCommand] = []
        self._next_order = 0

    def register(
        self,
        owner: str,
        command: NaturalCommand,
    ) -> None:
        """
        註冊一條自然語言指令。

        owner 用來標記指令屬於哪個 Module，
        方便 Module teardown 時一次解除。
        """

        normalized_owner = owner.strip()

        if not normalized_owner:
            raise ValueError(
                "Natural Command owner 不可為空"
            )

        regex = _compile_pattern(
            command.pattern
        )

        compiled = _CompiledCommand(
            owner=normalized_owner,
            command=command,
            regex=regex,
            order=self._next_order,
        )

        self._next_order += 1
        self._commands.append(compiled)

        self._sort()

    def register_many(
        self,
        owner: str,
        commands: tuple[NaturalCommand, ...],
    ) -> None:
        """一次註冊同一 Module 的多條自然語言指令。"""

        for command in commands:
            self.register(
                owner,
                command,
            )

    def unregister(
        self,
        owner: str,
    ) -> None:
        """
        移除某個 Module 註冊的全部自然語言指令。
        """

        normalized_owner = owner.strip()

        self._commands = [
            command
            for command in self._commands
            if command.owner != normalized_owner
        ]

    def _sort(self) -> None:
        """
        priority 高者優先。

        priority 相同時維持註冊順序，
        確保匹配結果固定且可預期。
        """

        self._commands.sort(
            key=lambda item: (
                -item.command.priority,
                item.order,
            )
        )

    # ── Dispatch ──────────────────────

    async def dispatch(
        self,
        message: discord.Message,
        prompt: str,
    ) -> bool:
        """
        嘗試將輸入匹配到已註冊的自然語言指令。

        True:
            已命中並交由 Feature Handler 處理。
            呼叫端不應再重複處理同一則訊息。

        False:
            沒有任何自然語言指令命中。
            可以交由其他訊息處理流程。
        """

        text = " ".join(
            prompt.strip().split()
        )

        if not text:
            return False

        for registered in self._commands:
            match = registered.regex.fullmatch(
                text
            )

            if match is None:
                continue

            parameters = {
                key: value.strip()
                for key, value
                in match.groupdict().items()
            }

            try:
                await registered.command.handler(
                    message,
                    parameters,
                )
            except Exception:
                logger.exception(
                    (
                        "Natural Command 執行失敗 "
                        "owner=%s pattern=%s"
                    ),
                    registered.owner,
                    registered.command.pattern,
                )
                try:
                    await message.reply(
                        "指令執行失敗，請稍後再試。"
                    )
                except discord.HTTPException:
                    logger.exception(
                        "Natural Command 錯誤回覆傳送失敗"
                    )

            # 已經匹配到自然語言指令。
            # 即使 Handler 執行失敗，也視為已命中，避免同一訊息被重複處理。
            return True

        return False

    # ── Inspection ──────────────────────

    def contains(
        self,
        prompt: str,
    ) -> bool:
        """
        只檢查輸入是否符合自然語言指令，
        不執行 Handler。

        可用於需要單純判斷：
            輸入是否已符合自然語言指令
        的地方。
        """

        text = " ".join(
            prompt.strip().split()
        )

        if not text:
            return False

        return any(
            registered.regex.fullmatch(text)
            is not None
            for registered in self._commands
        )


# ── Shared Registry ──────────────────────

natural_commands = NaturalCommandRegistry()


async def dispatch_message(
    message: discord.Message,
    registry: NaturalCommandRegistry = natural_commands,
    *,
    bot_user_id: int | None = None,
) -> bool:
    """只分派直接 @Bot 開頭的自然語言快捷指令。"""

    if message.author.bot or bot_user_id is None:
        return False

    mention_pattern = rf"^<@!?{bot_user_id}>\s*"
    match = re.match(mention_pattern, message.content)
    if match is None:
        return False

    prompt = message.content[match.end():]
    return await registry.dispatch(
        message,
        prompt,
    )
