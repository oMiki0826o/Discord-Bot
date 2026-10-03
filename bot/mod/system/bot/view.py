"""
bot/mod/system/bot/view.py

Modification():

- 提供 $bot 控制面板互動 View。
- 顯示 Bot Runtime、Module、設定 與 Presence 狀態。
- 支援控制面板頁面切換與重新整理。
- 支援重新載入全部 設定。
- 支援重新套用 Discord Presence。
- 限制控制面板僅能由原 Owner 操作。

本檔負責 System Module 的 Bot 控制面板顯示與互動。
"""

from __future__ import annotations

import time
from enum import Enum

import discord
from discord.ext import commands

from bot.core.modules.registry import ModuleStatus
from bot.core.settings.manager import get, settings


# ── Panel Page ──────────────────────

class PanelPage(str, Enum):
    OVERVIEW = "overview"
    MODULES = "modules"
    SETTINGS = "settings"
    PRESENCE = "presence"


# ── 格式化 ──────────────────────

def _format_uptime(seconds: float) -> str:
    """將執行秒數格式化為易讀時間。"""

    total_seconds = max(0, int(seconds))

    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    parts: list[str] = []

    if days:
        parts.append(f"{days} 天")

    if hours or days:
        parts.append(f"{hours} 小時")

    if minutes or hours or days:
        parts.append(f"{minutes} 分")

    parts.append(f"{seconds} 秒")

    return " ".join(parts)


def _get_settings_names() -> list[str]:
    """取得所有 設定 設定檔名稱。"""

    if not settings.settings_dir.exists():
        return []

    return sorted(
        path.stem
        for path in settings.settings_dir.glob("*.json")
    )


# ── Bot Panel ──────────────────────

class BotPanelView(discord.ui.View):
    """Bot System 控制面板。"""

    def __init__(
        self,
        bot: commands.Bot,
        owner_id: int,
    ) -> None:
        super().__init__(timeout=300)

        self.bot = bot
        self.owner_id = owner_id

        self.page = PanelPage.OVERVIEW
        self.message: discord.Message | None = None

        self._update_buttons()

    # ── 權限 ──────────────────────

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """限制控制面板只能由原 Owner 操作。"""

        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            "你沒有操作此控制面板的權限。",
            ephemeral=True,
        )

        return False

    # ── Embed ──────────────────────

    def build_overview_embed(self) -> discord.Embed:
        """建立 Bot Runtime 總覽。"""

        startup_time = getattr(
            self.bot,
            "startup_time",
            time.perf_counter(),
        )

        uptime = time.perf_counter() - startup_time
        latency = round(self.bot.latency * 1000)

        member_count = sum(
            guild.member_count or 0
            for guild in self.bot.guilds
        )

        loader = getattr(
            self.bot,
            "module_loader",
            None,
        )

        module_count = 0
        loaded_count = 0
        failed_count = 0

        if loader is not None:
            modules = loader.registry.all()

            module_count = len(modules)

            loaded_count = sum(
                module.status is ModuleStatus.LOADED
                for module in modules
            )

            failed_count = sum(
                module.status is ModuleStatus.FAILED
                for module in modules
            )

        settings_count = len(
            _get_settings_names()
        )

        embed = discord.Embed(
            title="Bot 控制面板",
            description="執行狀態總覽。",
        )

        embed.add_field(
            name="延遲",
            value=f"`{latency} ms`",
            inline=True,
        )

        embed.add_field(
            name="執行時間",
            value=f"`{_format_uptime(uptime)}`",
            inline=True,
        )

        embed.add_field(
            name="伺服器",
            value=f"`{len(self.bot.guilds)}`",
            inline=True,
        )

        embed.add_field(
            name="成員",
            value=f"`{member_count}`",
            inline=True,
        )

        embed.add_field(
            name="模組",
            value=(
                f"`{loaded_count}/{module_count}` 已載入\n"
                f"`{failed_count}` 載入失敗"
            ),
            inline=True,
        )

        embed.add_field(
            name="設定",
            value=f"`{settings_count}` 個檔案",
            inline=True,
        )

        return embed

    def build_modules_embed(self) -> discord.Embed:
        """建立 Module 狀態頁面。"""

        embed = discord.Embed(
            title="模組",
            description="目前模組載入狀態。",
        )

        loader = getattr(
            self.bot,
            "module_loader",
            None,
        )

        if loader is None:
            embed.description = (
                "模組載入器尚未初始化。"
            )
            return embed

        modules = loader.registry.all()

        if not modules:
            embed.description = (
                "目前沒有可用的模組。"
            )
            return embed

        lines = [
            f"`{module.name}` — {module.status.value}"
            for module in modules
        ]

        embed.description = "\n".join(lines)

        return embed

    def build_settings_embed(self) -> discord.Embed:
        """建立 設定 狀態頁面。"""

        names = _get_settings_names()

        embed = discord.Embed(
            title="設定",
            description="目前可用的 設定 設定檔。",
        )

        if not names:
            embed.description = (
                "目前沒有 設定 設定檔。"
            )
            return embed

        embed.add_field(
            name=f"設定檔 · {len(names)}",
            value="\n".join(
                f"`{name}.json`"
                for name in names
            ),
            inline=False,
        )

        return embed

    def build_presence_embed(self) -> discord.Embed:
        """建立 Presence 狀態頁面。"""

        activity = str(
            get(
                "bot.presence.activity",
                "listening",
            )
        )

        text = str(
            get(
                "bot.presence.text",
                "",
            )
        )

        status = str(
            get(
                "bot.presence.status",
                "online",
            )
        )

        embed = discord.Embed(
            title="Discord 狀態",
            description="目前套用的 Discord 狀態。",
        )

        embed.add_field(
            name="上線狀態",
            value=f"`{status}`",
            inline=True,
        )

        embed.add_field(
            name="活動類型",
            value=f"`{activity}`",
            inline=True,
        )

        embed.add_field(
            name="顯示文字",
            value=f"`{text or '未設定'}`",
            inline=False,
        )

        return embed

    def build_embed(self) -> discord.Embed:
        """依目前頁面建立 Embed。"""

        if self.page is PanelPage.MODULES:
            return self.build_modules_embed()

        if self.page is PanelPage.SETTINGS:
            return self.build_settings_embed()

        if self.page is PanelPage.PRESENCE:
            return self.build_presence_embed()

        return self.build_overview_embed()

    # ── View 狀態 ──────────────────────

    def _update_buttons(self) -> None:
        """依目前頁面更新 Button 狀態。"""

        self.overview_button.disabled = (
            self.page is PanelPage.OVERVIEW
        )

        self.modules_button.disabled = (
            self.page is PanelPage.MODULES
        )

        self.settings_button.disabled = (
            self.page is PanelPage.SETTINGS
        )

        self.presence_button.disabled = (
            self.page is PanelPage.PRESENCE
        )

        self.reload_settings_button.disabled = (
            self.page is not PanelPage.SETTINGS
        )

        self.reload_presence_button.disabled = (
            self.page is not PanelPage.PRESENCE
        )

    async def _change_page(
        self,
        interaction: discord.Interaction,
        page: PanelPage,
    ) -> None:
        """切換控制面板頁面。"""

        self.page = page

        self._update_buttons()

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self,
        )

    # ── 導覽 ──────────────────────

    @discord.ui.button(
        label="總覽",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def overview_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self._change_page(
            interaction,
            PanelPage.OVERVIEW,
        )

    @discord.ui.button(
        label="模組",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def modules_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self._change_page(
            interaction,
            PanelPage.MODULES,
        )

    @discord.ui.button(
        label="設定",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def settings_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self._change_page(
            interaction,
            PanelPage.SETTINGS,
        )

    @discord.ui.button(
        label="Discord 狀態",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def presence_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self._change_page(
            interaction,
            PanelPage.PRESENCE,
        )

    # ── 操作 ──────────────────────

    @discord.ui.button(
        label="重新整理",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def refresh_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """重新整理目前頁面。"""

        self._update_buttons()

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self,
        )

    @discord.ui.button(
        label="重新載入設定",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def reload_settings_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """重新載入全部 設定。"""

        try:
            settings.reload_all()
        except RuntimeError as exc:
            await interaction.response.send_message(
                str(exc),
                ephemeral=True,
            )
            return

        self._update_buttons()

        await interaction.response.edit_message(
            embed=self.build_settings_embed(),
            view=self,
        )

    @discord.ui.button(
        label="重新套用狀態",
        style=discord.ButtonStyle.secondary,
        row=1,
    )
    async def reload_presence_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        """重新套用 Discord Presence。"""

        refresh_presence = getattr(
            self.bot,
            "refresh_presence",
            None,
        )

        if refresh_presence is None:
            await interaction.response.send_message(
                "目前無法重新套用 Discord 狀態。",
                ephemeral=True,
            )
            return

        try:
            await refresh_presence()
        except discord.HTTPException as exc:
            await interaction.response.send_message(
                f"Discord 狀態更新失敗：`{exc}`",
                ephemeral=True,
            )
            return

        self._update_buttons()

        await interaction.response.edit_message(
            embed=self.build_presence_embed(),
            view=self,
        )

    # ── Timeout ──────────────────────

    async def on_timeout(self) -> None:
        """控制面板逾時後停用所有元件。"""

        for item in self.children:
            if isinstance(
                item,
                discord.ui.Button,
            ):
                item.disabled = True

        if self.message is None:
            return

        try:
            await self.message.edit(
                view=self
            )
        except discord.HTTPException:
            return