"""
bot/mod/message/autoreply/command.py

Modification():

- Administrator slash commands for managing auto-reply rules。
"""

from __future__ import annotations

import io
import json
import time

import discord
from discord import app_commands
from discord.ext import commands
import regex

from bot.mod.message.autoreply.matcher import AutoReplyMatcher, MatchInput
from bot.mod.message.autoreply.model import AutoReplyDocument, AutoReplyRule, MatchMode
from bot.mod.message.autoreply.repository import AutoReplyRepository
from bot.mod.message.autoreply.service import AutoReplyService


def _permission(interaction: discord.Interaction) -> bool:
    return (
        interaction.guild is not None
        and isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.manage_messages
    )


class AutoReplyCog(
    commands.GroupCog,
    group_name="autoreply",
    group_description="管理伺服器自動回覆規則。",
):
    def __init__(
        self,
        bot: commands.Bot,
        *,
        repository: AutoReplyRepository,
        matcher: AutoReplyMatcher,
        service: AutoReplyService,
        max_rules: int,
        default_cooldown_seconds: float,
    ) -> None:
        self.bot = bot
        self.repository = repository
        self.matcher = matcher
        self.service = service
        self.max_rules = max_rules
        self.default_cooldown_seconds = default_cooldown_seconds

    async def _guard(self, interaction: discord.Interaction) -> int | None:
        if not _permission(interaction):
            await interaction.response.send_message(
                "你需要「管理訊息」權限才能管理自動回覆。", ephemeral=True
            )
            return None
        return interaction.guild_id

    def _build_rule(
        self,
        *,
        rule_id: str,
        mode: str,
        pattern: str,
        response: str,
        priority: int,
        cooldown_seconds: float | None,
    ) -> AutoReplyRule:
        try:
            match_mode = MatchMode(mode.lower())
        except ValueError as exc:
            raise ValueError("模式只能是 exact、contains 或 regex") from exc
        if match_mode is MatchMode.REGEX:
            try:
                regex.compile(pattern)
            except regex.error as exc:
                raise ValueError(f"正規表示式錯誤: {exc}") from exc
        rule = AutoReplyRule(
            id=rule_id.strip(), enabled=True, priority=priority, mode=match_mode,
            pattern=pattern, case_sensitive=False, response=response,
            cooldown_seconds=(
                self.default_cooldown_seconds
                if cooldown_seconds is None
                else cooldown_seconds
            ),
        )
        rule.validate()
        return rule

    async def _save_rule(self, interaction: discord.Interaction, rule: AutoReplyRule, *, edit: bool) -> None:
        guild_id = await self._guard(interaction)
        if guild_id is None:
            return
        document = self.repository.load(guild_id)
        existing = {item.id: item for item in document.rules}
        if edit and rule.id not in existing:
            await interaction.response.send_message("找不到指定規則。", ephemeral=True)
            return
        if not edit and rule.id in existing:
            await interaction.response.send_message("規則 ID 已存在，請使用 edit。", ephemeral=True)
            return
        existing[rule.id] = rule
        if len(existing) > self.max_rules:
            await interaction.response.send_message("此伺服器的自動回覆規則已達上限。", ephemeral=True)
            return
        self.repository.save(guild_id, AutoReplyDocument(1, guild_id, tuple(existing.values())))
        await interaction.response.send_message(f"已儲存規則 `{rule.id}`。", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        await self.service.handle_message(message)

    @app_commands.command(name="list", description="列出自動回覆規則。")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def list_rules(self, interaction: discord.Interaction) -> None:
        guild_id = await self._guard(interaction)
        if guild_id is None:
            return
        rules = self.repository.load(guild_id).rules
        text = "\n".join(
            f"`{rule.id}` {'啟用' if rule.enabled else '停用'} | {rule.mode.value} | 優先 {rule.priority}"
            for rule in sorted(rules, key=lambda item: (-item.priority, item.id))
        ) or "目前沒有自動回覆規則。"
        await interaction.response.send_message(text[:2000], ephemeral=True)

    @app_commands.command(name="add", description="新增自動回覆規則。")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def add(
        self, interaction: discord.Interaction, rule_id: str, mode: str,
        pattern: str, response: str, priority: int = 0,
        cooldown_seconds: float | None = None,
    ) -> None:
        try:
            rule = self._build_rule(
                rule_id=rule_id, mode=mode, pattern=pattern, response=response,
                priority=priority, cooldown_seconds=cooldown_seconds,
            )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await self._save_rule(interaction, rule, edit=False)

    @app_commands.command(name="edit", description="修改自動回覆規則。")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def edit(
        self, interaction: discord.Interaction, rule_id: str, mode: str,
        pattern: str, response: str, priority: int = 0,
        cooldown_seconds: float | None = None,
    ) -> None:
        try:
            rule = self._build_rule(
                rule_id=rule_id, mode=mode, pattern=pattern, response=response,
                priority=priority, cooldown_seconds=cooldown_seconds,
            )
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await self._save_rule(interaction, rule, edit=True)

    async def _toggle(self, interaction: discord.Interaction, rule_id: str, enabled: bool) -> None:
        guild_id = await self._guard(interaction)
        if guild_id is None:
            return
        document = self.repository.load(guild_id)
        updated = []
        found = False
        for rule in document.rules:
            if rule.id == rule_id:
                values = rule.to_dict()
                values["enabled"] = enabled
                rule = AutoReplyRule.from_dict(values)
                found = True
            updated.append(rule)
        if not found:
            await interaction.response.send_message("找不到指定規則。", ephemeral=True)
            return
        self.repository.save(guild_id, AutoReplyDocument(1, guild_id, tuple(updated)))
        await interaction.response.send_message(f"已{'啟用' if enabled else '停用'} `{rule_id}`。", ephemeral=True)

    @app_commands.command(name="enable", description="啟用規則。")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def enable(self, interaction: discord.Interaction, rule_id: str) -> None:
        await self._toggle(interaction, rule_id, True)

    @app_commands.command(name="disable", description="停用規則。")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def disable(self, interaction: discord.Interaction, rule_id: str) -> None:
        await self._toggle(interaction, rule_id, False)

    @app_commands.command(name="delete", description="刪除規則。")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def delete(self, interaction: discord.Interaction, rule_id: str) -> None:
        guild_id = await self._guard(interaction)
        if guild_id is None:
            return
        document = self.repository.load(guild_id)
        rules = tuple(rule for rule in document.rules if rule.id != rule_id)
        if len(rules) == len(document.rules):
            await interaction.response.send_message("找不到指定規則。", ephemeral=True)
            return
        self.repository.save(guild_id, AutoReplyDocument(1, guild_id, rules))
        await interaction.response.send_message(f"已刪除 `{rule_id}`。", ephemeral=True)

    @app_commands.command(name="test", description="測試文字會命中哪條規則。")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def test(self, interaction: discord.Interaction, content: str) -> None:
        guild_id = await self._guard(interaction)
        if guild_id is None or interaction.guild is None or interaction.channel is None:
            return
        found = self.matcher.find(
            self.repository.load(guild_id),
            MatchInput(
                guild_id, interaction.channel.id, interaction.user.id, content,
                interaction.user.display_name, interaction.user.mention,
                getattr(interaction.channel, "mention", "#頻道"), interaction.guild.name,
            ),
            now=time.monotonic(), consume_cooldown=False,
        )
        text = f"命中 `{found.rule_id}`：\n{found.rendered_response}" if found else "沒有命中任何規則。"
        await interaction.response.send_message(text[:2000], ephemeral=True)

    @app_commands.command(name="export", description="匯出自動回覆 JSON。")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def export(self, interaction: discord.Interaction) -> None:
        guild_id = await self._guard(interaction)
        if guild_id is None:
            return
        await interaction.response.send_message(
            file=discord.File(io.BytesIO(self.repository.export_bytes(guild_id)), filename=f"autoreplies-{guild_id}.json"),
            ephemeral=True,
        )

    @app_commands.command(name="import", description="匯入並取代自動回覆 JSON。")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    async def import_rules(self, interaction: discord.Interaction, attachment: discord.Attachment) -> None:
        guild_id = await self._guard(interaction)
        if guild_id is None:
            return
        if attachment.size > 1_048_576 or not attachment.filename.lower().endswith(".json"):
            await interaction.response.send_message("只接受 1 MiB 以下的 JSON 檔案。", ephemeral=True)
            return
        try:
            raw = json.loads((await attachment.read()).decode("utf-8"))
            document = AutoReplyDocument.from_dict(raw)
            if document.guild_id != guild_id or len(document.rules) > self.max_rules:
                raise ValueError("Guild 不符或規則超過上限")
            for rule in document.rules:
                if rule.mode is MatchMode.REGEX:
                    regex.compile(rule.pattern)
            self.repository.save(guild_id, document)
        except (UnicodeError, json.JSONDecodeError, ValueError, regex.error) as exc:
            await interaction.response.send_message(f"匯入失敗：{exc}", ephemeral=True)
            return
        await interaction.response.send_message(f"已匯入 `{len(document.rules)}` 條規則。", ephemeral=True)
