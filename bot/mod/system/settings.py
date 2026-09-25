"""
bot/mod/system/settings.py

Modification():

- 提供 Owner 專用 Settings 管理指令。
- 支援查看可用 Settings 設定檔。
- 支援查看指定 Settings 內容。
- 支援重新載入單一或全部 Settings。

本檔提供 Bot 非機密 Settings 的 Owner 管理介面。
"""

from __future__ import annotations

import json

import discord
from discord.ext import commands

from bot.core.settings.manager import settings


# ── Settings 顯示 ──────────────────────

def _get_settings_names() -> list[str]:
    """取得 settings/ 內所有 JSON 設定檔名稱。"""

    if not settings.settings_dir.exists():
        return []

    return sorted(
        path.stem
        for path in settings.settings_dir.glob("*.json")
    )


def _format_settings(data: dict[str, object]) -> str:
    """將 Settings 格式化為 Discord Code Block 內容。"""

    return json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
    )


async def _reload_module_for_settings(
    bot: commands.Bot,
    name: str,
) -> bool:
    """重新建立使用指定 Module Settings 的 Runtime 元件。"""

    loader = getattr(bot, "module_loader", None)
    if loader is None or name in {"bot", "modules"}:
        return True

    if loader.registry.get(name) is None:
        return True

    return await loader.reload(name)


# ── Settings 管理 ──────────────────────

class SettingsManagementCog(commands.Cog):
    """提供 Owner 專用 Settings 管理指令。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.group(name="settings", invoke_without_command=True)
    @commands.is_owner()
    async def settings_group(
        self,
        ctx: commands.Context,
    ) -> None:
        """顯示 Settings 管理概要。"""

        names = _get_settings_names()

        embed = discord.Embed(
            title="設定管理",
            description=(
                f"設定檔數量：`{len(names)}`\n\n"
                "`$settings show [name]`\n"
                "`$settings reload [name]`\n"
                "`$settings reload-all`"
            ),
        )

        if names:
            embed.add_field(
                name="設定檔",
                value="\n".join(
                    f"`{name}`"
                    for name in names
                ),
                inline=False,
            )

        embed.set_footer(
            text="$help settings 查看詳細用法"
        )

        await ctx.send(embed=embed)

    # ── 查看 Settings ──────────────────────

    @settings_group.command(name="show")
    @commands.is_owner()
    async def settings_show(
        self,
        ctx: commands.Context,
        name: str | None = None,
    ) -> None:
        """查看 Settings 設定檔。"""

        names = _get_settings_names()

        if name is None:
            if not names:
                await ctx.send("目前沒有 Settings 設定檔。")
                return

            embed = discord.Embed(
                title="設定",
                description="\n".join(
                    f"`{settings_name}`"
                    for settings_name in names
                ),
            )

            await ctx.send(embed=embed)
            return

        if name not in names:
            await ctx.send(
                f"找不到 Settings：`{name}`"
            )
            return

        try:
            data = settings.load(name)
        except RuntimeError as exc:
            await ctx.send(str(exc))
            return

        content = _format_settings(data)

        if len(content) > 3900:
            await ctx.send(
                f"`{name}.json` 內容過長，無法直接顯示。"
            )
            return

        embed = discord.Embed(
            title=f"{name}.json",
            description=f"```json\n{content}\n```",
        )

        await ctx.send(embed=embed)

    # ── 重新載入 Settings ──────────────────────

    @settings_group.command(name="reload")
    @commands.is_owner()
    async def settings_reload(
        self,
        ctx: commands.Context,
        name: str | None = None,
    ) -> None:
        """重新載入指定 Settings。"""

        if name is None:
            await ctx.send(
                "請指定 Settings 名稱。\n"
                "用法：`$settings reload <name>`"
            )
            return

        names = _get_settings_names()

        if name not in names:
            await ctx.send(
                f"找不到 Settings：`{name}`"
            )
            return

        try:
            settings.reload(name)
            reloaded = await _reload_module_for_settings(
                self.bot,
                name,
            )
        except RuntimeError as exc:
            await ctx.send(str(exc))
            return

        if not reloaded:
            await ctx.send(f"Settings 已重新載入，但 Module 重載失敗：`{name}`")
            return

        await ctx.send(f"已重新載入 Settings：`{name}`")

    @settings_group.command(name="reload-all")
    @commands.is_owner()
    async def settings_reload_all(
        self,
        ctx: commands.Context,
    ) -> None:
        """重新載入全部 Settings。"""

        try:
            settings.reload_all()
            for settings_name in _get_settings_names():
                await _reload_module_for_settings(
                    self.bot,
                    settings_name,
                )
        except RuntimeError as exc:
            await ctx.send(str(exc))
            return

        names = _get_settings_names()

        await ctx.send(
            f"已重新載入全部 Settings，共 `{len(names)}` 個設定檔。"
        )
