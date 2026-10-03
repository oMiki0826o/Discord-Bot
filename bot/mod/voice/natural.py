"""
bot/mod/voice/natural.py

Modification():

- 宣告 Voice Module 支援的自然語言指令格式。
- 將自然語言指令轉接至 Voice Command 的共用執行介面。
- 將 Command 執行結果回覆至原始 Discord 訊息頻道。

本檔僅負責 Natural Command 與 Voice Command 之間的轉接。
語音頻道權限、資料庫與 Discord 頻道操作均由 command.py 負責。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping

import discord

from bot.core.discord.natural_command import NaturalCommand
from bot.mod.voice.command import VoiceChannel, VoiceCommandResult


# ── 型別 ──────────────────────

VoiceExecutor = Callable[
    [discord.Member],
    Awaitable[VoiceCommandResult],
]


# ── 共用驗證 ──────────────────────

async def _get_member(
    message: discord.Message,
) -> discord.Member | None:
    """取得伺服器中的訊息發送者。"""

    if message.guild is None:
        await message.reply(
            "此功能僅限伺服器使用",
            mention_author=False,
        )
        return None

    if not isinstance(
        message.author,
        discord.Member,
    ):
        await message.reply(
            "無法取得您的伺服器成員資訊",
            mention_author=False,
        )
        return None

    return message.author


async def _reply_result(
    message: discord.Message,
    result: VoiceCommandResult,
) -> None:
    """將 Voice Command 的結果回覆至原始訊息。"""

    await message.reply(
        result.message,
        mention_author=False,
    )


async def _execute_simple(
    message: discord.Message,
    executor: VoiceExecutor,
) -> None:
    """執行不帶額外參數的 Voice Command。"""

    member = await _get_member(
        message
    )

    if member is None:
        return

    result = await executor(
        member
    )

    await _reply_result(
        message,
        result,
    )


# ── Natural Handlers ──────────────────────

async def _create(
    voice: VoiceChannel,
    message: discord.Message,
    parameters: Mapping[str, str],
) -> None:
    """轉接「建立語音」。"""

    await _execute_simple(
        message,
        voice.execute_create,
    )


async def _name(
    voice: VoiceChannel,
    message: discord.Message,
    parameters: Mapping[str, str],
) -> None:
    """轉接「語音名稱 {name}」。"""

    member = await _get_member(
        message
    )

    if member is None:
        return

    result = await voice.execute_name(
        member,
        parameters["name"],
    )

    await _reply_result(
        message,
        result,
    )


async def _limit(
    voice: VoiceChannel,
    message: discord.Message,
    parameters: Mapping[str, str],
) -> None:
    """轉接「語音上限 {limit}」。"""

    member = await _get_member(
        message
    )

    if member is None:
        return

    raw_limit = parameters["limit"].strip()

    try:
        limit = int(
            raw_limit
        )
    except ValueError:
        await message.reply(
            "語音上限必須是 0 到 99 的整數",
            mention_author=False,
        )
        return

    result = await voice.execute_limit(
        member,
        limit,
    )

    await _reply_result(
        message,
        result,
    )


async def _lock(
    voice: VoiceChannel,
    message: discord.Message,
    parameters: Mapping[str, str],
) -> None:
    """轉接「上鎖語音」。"""

    await _execute_simple(
        message,
        voice.execute_lock,
    )


async def _unlock(
    voice: VoiceChannel,
    message: discord.Message,
    parameters: Mapping[str, str],
) -> None:
    """轉接「解鎖語音」。"""

    await _execute_simple(
        message,
        voice.execute_unlock,
    )


# ── Command 宣告 ──────────────────────

def create_natural_commands(
    voice: VoiceChannel,
) -> tuple[NaturalCommand, ...]:
    """
    建立 Voice Module 的 Natural Command 宣告。

    Core 僅負責格式匹配與參數擷取；
    實際 Voice 操作仍由 command.py 執行。
    """

    async def create_handler(
        message: discord.Message,
        parameters: Mapping[str, str],
    ) -> None:
        await _create(
            voice,
            message,
            parameters,
        )

    async def name_handler(
        message: discord.Message,
        parameters: Mapping[str, str],
    ) -> None:
        await _name(
            voice,
            message,
            parameters,
        )

    async def limit_handler(
        message: discord.Message,
        parameters: Mapping[str, str],
    ) -> None:
        await _limit(
            voice,
            message,
            parameters,
        )

    async def lock_handler(
        message: discord.Message,
        parameters: Mapping[str, str],
    ) -> None:
        await _lock(
            voice,
            message,
            parameters,
        )

    async def unlock_handler(
        message: discord.Message,
        parameters: Mapping[str, str],
    ) -> None:
        await _unlock(
            voice,
            message,
            parameters,
        )

    return (
        NaturalCommand(
            pattern="建立語音",
            handler=create_handler,
        ),
        NaturalCommand(
            pattern="語音名稱 {name}",
            handler=name_handler,
        ),
        NaturalCommand(
            pattern="語音上限 {limit}",
            handler=limit_handler,
        ),
        NaturalCommand(
            pattern="上鎖語音",
            handler=lock_handler,
        ),
        NaturalCommand(
            pattern="解鎖語音",
            handler=unlock_handler,
        ),
    )