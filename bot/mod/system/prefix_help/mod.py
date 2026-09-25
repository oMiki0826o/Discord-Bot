"""
bot/mod/system/prefix_help/mod.py

Modification():

- 提供 Owner 專用 Module 管理指令。
- 支援查看、載入、卸載與重新載入 Module。
- 支援重新載入所有目前已載入的 Module。

本檔提供 System Module 的 Module Runtime 管理介面。
"""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.core.modules.registry import ModuleStatus


# ── Module 管理 ──────────────────────

class ModuleManagementCog(commands.Cog):
    """提供 Owner 專用 Module 管理指令。"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _get_loader(self):
        loader = getattr(self.bot, "module_loader", None)

        if loader is None:
            raise RuntimeError("ModuleLoader 尚未初始化。")

        return loader

    @commands.group(name="mod", invoke_without_command=True)
    @commands.is_owner()
    async def mod(self, ctx: commands.Context) -> None:
        """顯示 Module 管理概要。"""

        loader = self._get_loader()
        modules = loader.registry.all()

        loaded = sum(
            module.status is ModuleStatus.LOADED
            for module in modules
        )
        failed = sum(
            module.status is ModuleStatus.FAILED
            for module in modules
        )

        embed = discord.Embed(
            title="模組管理",
            description=(
                f"模組：`{len(modules)}`\n"
                f"Loaded：`{loaded}`\n"
                f"Failed：`{failed}`"
            ),
        )

        embed.set_footer(text="$help mod 查看詳細用法")

        await ctx.send(embed=embed)

    @mod.command(name="list")
    @commands.is_owner()
    async def mod_list(self, ctx: commands.Context) -> None:
        """列出所有已發現的 Module。"""

        loader = self._get_loader()
        modules = loader.registry.all()

        if not modules:
            await ctx.send("目前沒有已發現的 Module。")
            return

        lines = [
            f"`{module.name}` — {module.status.value}"
            for module in modules
        ]

        embed = discord.Embed(
            title="模組",
            description="\n".join(lines),
        )

        await ctx.send(embed=embed)

    @mod.command(name="load")
    @commands.is_owner()
    async def mod_load(
        self,
        ctx: commands.Context,
        module_name: str,
    ) -> None:
        """載入指定 Module。"""

        loader = self._get_loader()

        success = await loader.load(module_name)

        if success:
            await ctx.send(f"已載入 Module：`{module_name}`")
            return

        await ctx.send(f"Module 載入失敗：`{module_name}`")

    @mod.command(name="enable")
    @commands.is_owner()
    async def mod_enable(self, ctx: commands.Context, module_name: str) -> None:
        """啟用 Module 並立即載入。"""

        if module_name == "system":
            await ctx.send("System Module 不可停用。")
            return

        if await self._get_loader().enable(module_name):
            await ctx.send(f"已啟用 Module：`{module_name}`")
            return
        await ctx.send(f"Module 啟用失敗：`{module_name}`")

    @mod.command(name="disable")
    @commands.is_owner()
    async def mod_disable(self, ctx: commands.Context, module_name: str) -> None:
        """停用 Module 並卸載。"""

        if module_name == "system":
            await ctx.send("不能停用 System Module。")
            return

        if await self._get_loader().disable(module_name):
            await ctx.send(f"已停用 Module：`{module_name}`")
            return
        await ctx.send(f"Module 停用失敗：`{module_name}`")

    @mod.command(name="unload")
    @commands.is_owner()
    async def mod_unload(
        self,
        ctx: commands.Context,
        module_name: str,
    ) -> None:
        """卸載指定 Module。"""

        if module_name == "system":
            await ctx.send("不能透過 `$mod unload` 卸載 System Module。")
            return

        loader = self._get_loader()

        success = await loader.unload(module_name)

        if success:
            await ctx.send(f"已卸載 Module：`{module_name}`")
            return

        await ctx.send(f"Module 卸載失敗：`{module_name}`")

    @mod.command(name="reload")
    @commands.is_owner()
    async def mod_reload(
        self,
        ctx: commands.Context,
        module_name: str,
    ) -> None:
        """重新載入指定 Module。"""

        if module_name == "system":
            await ctx.send(
                "System Module 不支援透過自身指令重新載入。"
            )
            return

        loader = self._get_loader()

        success = await loader.reload(module_name)

        if success:
            await ctx.send(f"已重新載入 Module：`{module_name}`")
            return

        await ctx.send(f"Module 重新載入失敗：`{module_name}`")

    @mod.command(name="reload-all")
    @commands.is_owner()
    async def mod_reload_all(
        self,
        ctx: commands.Context,
    ) -> None:
        """重新載入目前已載入的 模組。"""

        loader = self._get_loader()

        module_names = [
            module.name
            for module in loader.registry.loaded()
            if module.name != "system"
        ]

        if not module_names:
            await ctx.send("目前沒有可重新載入的 Module。")
            return

        succeeded: list[str] = []
        failed: list[str] = []

        for module_name in module_names:
            if await loader.reload(module_name):
                succeeded.append(module_name)
            else:
                failed.append(module_name)

        embed = discord.Embed(
            title="模組重新載入",
        )

        embed.add_field(
            name="成功",
            value=(
                "\n".join(f"`{name}`" for name in succeeded)
                if succeeded
                else "無"
            ),
            inline=True,
        )

        embed.add_field(
            name="失敗",
            value=(
                "\n".join(f"`{name}`" for name in failed)
                if failed
                else "無"
            ),
            inline=True,
        )

        await ctx.send(embed=embed)
