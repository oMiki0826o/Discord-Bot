"""
bot/mod/music/natural.py

Modification():

- 定義 Music Module 的自然語言指令。
- 將自然語言參數轉交 Music Command 共用執行介面。
- 將 Music Command 執行結果回覆至原始 Discord 訊息頻道。

本檔只負責自然語言指令與 Music Command 之間的轉接。
不直接操作 Player、Queue、Service 或其他音樂業務元件。
"""

from __future__ import annotations

# ── Standard Library ──────────────────────

from collections.abc import Awaitable, Callable, Mapping

# ── Third Party ──────────────────────

import discord

# ── Project ──────────────────────

from bot.core.discord.natural_command import NaturalCommand
from bot.mod.music.command import Music, MusicCommandResult


# ── Types ──────────────────────

MusicExecutor = Callable[
    [discord.Member],
    Awaitable[MusicCommandResult],
]


# ── 共用轉接 ──────────────────────

async def _get_member(message: discord.Message) -> discord.Member | None:
    """取得自然語言指令發話者的伺服器成員。"""

    if message.guild is None:
        await message.reply("此功能僅限伺服器使用")
        return None

    if not isinstance(message.author, discord.Member):
        await message.reply("無法取得伺服器成員資訊")
        return None

    return message.author


async def _reply_result(
    message: discord.Message,
    result: MusicCommandResult,
) -> None:
    """回覆 Music Command 的共用執行結果。"""

    if result.embed is None:
        await message.reply(result.message)
        return

    kwargs: dict[str, object] = {
        "embed": result.embed,
    }
    if result.view is not None:
        kwargs["view"] = result.view

    await message.reply(**kwargs)


async def _execute(
    message: discord.Message,
    executor: MusicExecutor,
) -> None:
    """將無額外參數的自然語言指令轉交共用 Command。"""

    member = await _get_member(message)
    if member is None:
        return

    result = await executor(member)
    await _reply_result(message, result)


# ── Natural Command Factory ──────────────────────

def create_natural_commands(music: Music) -> tuple[NaturalCommand, ...]:
    """建立 Music Module 的自然語言指令集合。"""

    async def play(
        message: discord.Message,
        params: Mapping[str, str],
    ) -> None:
        member = await _get_member(message)
        if member is None:
            return

        url = params.get("url", "").strip()
        if not url:
            await message.reply("請提供要播放的 YouTube 網址")
            return

        result = await music.execute_play(
            member,
            message.channel,
            url,
        )
        await _reply_result(message, result)

    def simple(
        executor: MusicExecutor,
    ) -> Callable[[discord.Message, Mapping[str, str]], Awaitable[None]]:
        async def handler(
            message: discord.Message,
            params: Mapping[str, str],
        ) -> None:
            del params
            await _execute(message, executor)

        return handler

    return (
        NaturalCommand(pattern="播放 {url}", handler=play),
        NaturalCommand(pattern="暫停", handler=simple(music.execute_pause)),
        NaturalCommand(pattern="繼續", handler=simple(music.execute_resume)),
        NaturalCommand(pattern="跳過", handler=simple(music.execute_skip)),
        NaturalCommand(pattern="離開語音", handler=simple(music.execute_leave)),
    )
