"""
bot/mod/basic/help/view.py

Modification():

- 建立 Help Discord UI。
- 提供 Help 分類選擇功能。
- 提供 Help 分頁切換功能。
- 管理 Help Embed 顯示。

本檔只負責 Help 系統的 Discord UI，
不負責 Slash Command 掃描或 Help 資料建立。
"""

from __future__ import annotations

import discord

from bot.mod.basic.help.models import (
    HelpCategory,
    HelpPage,
)


# ── Help View ──────────────────────

class HelpView(discord.ui.View):
    """管理 Help 分類與分頁 UI。"""

    def __init__(
        self,
        categories: tuple[HelpCategory, ...],
        *,
        user_id: int,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(
            timeout=timeout
        )

        if not categories:
            raise ValueError(
                "HelpView 至少需要一個 HelpCategory"
            )

        self.categories = categories
        self.user_id = user_id
        self.message: discord.Message | None = None

        self.category_index = 0
        self.page_index = 0

        self.category_select = HelpCategorySelect(
            self
        )

        self.add_item(
            self.category_select
        )

        self._update_buttons()



    # ── 權限與逾時 ──────────────────────

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        """只允許開啟 Help 的使用者操作此面板。"""

        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這個指令面板是其他使用者開啟的，請使用 `/help` 開啟自己的面板。",
            ephemeral=True,
        )
        return False

    async def on_timeout(self) -> None:
        """逾時後停用互動元件，避免留下失效按鈕。"""

        for item in self.children:
            item.disabled = True

        if self.message is None:
            return

        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            return

    # ── Current ──────────────────────

    @property
    def current_category(
        self,
    ) -> HelpCategory:
        """取得目前分類。"""

        return self.categories[
            self.category_index
        ]


    @property
    def current_page(
        self,
    ) -> HelpPage:
        """取得目前分頁。"""

        return self.current_category.pages[
            self.page_index
        ]


    # ── Embed ──────────────────────

    def build_embed(
        self,
    ) -> discord.Embed:
        """建立目前 Help 分頁 Embed。"""

        category = self.current_category
        page = self.current_page

        embed = discord.Embed(
            title=f"指令說明｜{category.name}",
            color=discord.Color.blurple(),
        )

        if not page.entries:
            embed.description = (
                "此分類目前沒有可顯示的指令。"
            )

        else:
            lines = [
                (
                    f"`/{entry.name}`\n"
                    f"{entry.description}"
                )
                for entry in page.entries
            ]

            embed.description = "\n\n".join(
                lines
            )

        embed.set_footer(
            text=(
                f"第 {self.page_index + 1}／{len(category.pages)} 頁"
            )
        )

        return embed


    # ── UI 狀態 ──────────────────────

    def _update_buttons(
        self,
    ) -> None:
        """依目前分頁更新按鈕狀態。"""

        page_count = len(
            self.current_category.pages
        )

        self.previous_page.disabled = (
            self.page_index <= 0
        )

        self.next_page.disabled = (
            self.page_index >= page_count - 1
        )


    async def refresh(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """重新繪製 Help 訊息。"""

        self._update_buttons()

        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self,
        )


    # ── Page Buttons ──────────────────────

    @discord.ui.button(
        label="上一頁",
        style=discord.ButtonStyle.secondary,
    )
    async def previous_page(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """切換至上一頁。"""

        if self.page_index > 0:
            self.page_index -= 1

        await self.refresh(
            interaction
        )


    @discord.ui.button(
        label="下一頁",
        style=discord.ButtonStyle.secondary,
    )
    async def next_page(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        """切換至下一頁。"""

        if (
            self.page_index
            < len(self.current_category.pages) - 1
        ):
            self.page_index += 1

        await self.refresh(
            interaction
        )


# ── Category Select ──────────────────────

class HelpCategorySelect(discord.ui.Select):
    """Help 分類選單。"""

    def __init__(
        self,
        view: HelpView,
    ) -> None:
        self.help_view = view

        options = [
            discord.SelectOption(
                label=category.name,
                value=str(index),
            )
            for index, category
            in enumerate(view.categories)
        ]

        super().__init__(
            placeholder="選擇指令分類",
            min_values=1,
            max_values=1,
            options=options,
        )


    async def callback(
        self,
        interaction: discord.Interaction,
    ) -> None:
        """處理分類切換。"""

        self.help_view.category_index = int(
            self.values[0]
        )

        self.help_view.page_index = 0

        await self.help_view.refresh(
            interaction
        )