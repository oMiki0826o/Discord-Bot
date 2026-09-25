"""
bot/mod/voice/confirmation.py

Modification():

- 提供 Voice Module 自有的二次確認 View。
- 提供確認操作的權限檢查與執行保護。
- 確認時重新驗證指定的使用者與 Bot Guild 權限。

本檔負責 Voice Module 的確認互動。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord


Action = Callable[[discord.Interaction], Awaitable[None]]


# ── Permission Helpers ──────────────────────

def missing_permissions(
    interaction: discord.Interaction,
    *,
    user: tuple[str, ...] = (),
    bot: tuple[str, ...] = (),
) -> str | None:
    """回傳第一個缺少的權限訊息，全部具備則回傳 None。"""

    guild = interaction.guild
    member = interaction.user

    if guild is None or not isinstance(member, discord.Member):
        return "此操作僅限伺服器使用。"

    for permission in user:
        if not getattr(member.guild_permissions, permission, False):
            return f"你缺少 `{permission}` 權限。"

    bot_member = guild.me
    if bot_member is None:
        return "無法取得 Bot 權限資料。"

    for permission in bot:
        if not getattr(bot_member.guild_permissions, permission, False):
            return f"Bot 缺少 `{permission}` 權限。"

    return None


def guarded_action(
    action: Action,
    *,
    user: tuple[str, ...] = (),
    bot: tuple[str, ...] = (),
) -> Action:
    """建立確認時會重新驗證權限的 Action。"""

    async def guarded(interaction: discord.Interaction) -> None:
        error = missing_permissions(interaction, user=user, bot=bot)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        await action(interaction)

    return guarded


# ── Confirmation View ──────────────────────

class ConfirmationView(discord.ui.View):
    """限制只有原發起者可執行確認或取消。"""

    def __init__(
        self,
        *,
        user_id: int,
        action: Action,
        timeout: float = 60,
    ) -> None:
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.action = action

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "這不是你的確認面板。",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="確認", style=discord.ButtonStyle.danger)
    async def confirm(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self.action(interaction)
        self.stop()

    @discord.ui.button(label="取消", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await interaction.response.edit_message(
            content="已取消操作。",
            embed=None,
            view=None,
        )
        self.stop()


async def request_confirmation(
    interaction: discord.Interaction,
    *,
    title: str,
    description: str,
    action: Action,
) -> None:
    """送出 Voice Module 的二次確認介面。"""

    await interaction.response.send_message(
        embed=discord.Embed(
            title=title,
            description=description,
            color=discord.Color.orange(),
        ),
        view=ConfirmationView(
            user_id=interaction.user.id,
            action=action,
        ),
        ephemeral=True,
    )
