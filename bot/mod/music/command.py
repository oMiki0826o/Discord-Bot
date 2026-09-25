"""
bot/mod/music/command.py

Modification():

- 提供音樂播放的 Slash Commands 與事件監聽。
- 提供 Slash Command 與 Natural Command 共用的音樂操作介面。
- 提供 /play 快速播放與 /music 音樂功能面板。
- 提供 $musicstatus Owner Only 狀態查詢。
- 統一處理播放器語音頻道驗證與控制權限。

本檔負責 Music Module 的 Discord Command 與共用音樂操作。
Natural Command 僅呼叫本檔提供的 execute_* 方法，不直接操作
Player、Queue 或其他 Music Module 內部元件。
"""

from __future__ import annotations

# ── Standard Library ──────────────────────

import logging
from dataclasses import dataclass

# ── Third Party ──────────────────────

import discord
from discord import app_commands
from discord.ext import commands

# ── Project ──────────────────────

from bot.mod.music.embeds import (
    added_song_embed,
    error_embed,
    info_embed,
    music_panel_embed,
    now_playing_embed,
    playlist_added_embed,
)
from bot.mod.music.queue import QueueFullError
from bot.mod.music.service import get_manager, get_player, remove_player
from bot.mod.music.song import Song
from bot.mod.music.url import is_youtube_url
from bot.mod.music.views import MusicControls, MusicPanelView


log = logging.getLogger("bot.music")


# ── Command 結果 ──────────────────────

@dataclass(frozen=True, slots=True)
class MusicCommandResult:
    """Music Command 共用執行結果。"""

    success: bool
    message: str
    embed: discord.Embed | None = None
    view: discord.ui.View | None = None
    song: Song | None = None
    track_now_playing: bool = False


# ── Music Cog ──────────────────────

class Music(commands.Cog):
    """音樂播放相關的 Slash Commands、共用操作與事件監聽。"""

    def __init__(
        self,
        bot: commands.Bot,
    ) -> None:
        self.bot = bot

    # ── 共用驗證 ──────────────────────

    @staticmethod
    def _get_voice_channel(
        member: discord.Member,
    ) -> discord.VoiceChannel | None:
        """取得成員目前所在的一般語音頻道。"""

        if (
            member.voice is None
            or member.voice.channel is None
        ):
            return None

        channel = member.voice.channel

        if not isinstance(
            channel,
            discord.VoiceChannel,
        ):
            return None

        return channel

    @staticmethod
    def _can_move_player(
        member: discord.Member,
        player,
        channel: discord.VoiceChannel,
    ) -> bool:
        """
        判斷成員是否可以將播放器移動至指定頻道。

        播放器目前所在頻道仍有真人聽眾時，
        只有 Administrator 可以將 Bot 移至其他頻道。
        """

        current = player.voice_channel

        if (
            not player.is_connected
            or current is None
            or current.id == channel.id
        ):
            return True

        if member.guild_permissions.administrator:
            return True

        listeners = [
            voice_member
            for voice_member in current.members
            if not voice_member.bot
        ]

        return not listeners

    @staticmethod
    def _can_control_player(
        member: discord.Member,
        player,
    ) -> bool:
        """
        判斷成員是否可以控制目前播放器。

        Administrator 可以直接控制；
        一般成員必須與 Bot 位於相同語音頻道。
        """

        if member.guild_permissions.administrator:
            return True

        current = player.voice_channel

        if current is None:
            return False

        channel = Music._get_voice_channel(
            member
        )

        if channel is None:
            return False

        return current.id == channel.id

    # ── 共用播放 Command ──────────────────────

    async def execute_play(
        self,
        member: discord.Member,
        response_channel: discord.abc.Messageable,
        url: str,
        *,
        mode: str = "song",
    ) -> MusicCommandResult:
        """播放單曲或播放清單，供 Slash 與 Natural Command 共用。"""

        voice_channel = self._get_voice_channel(member)
        if voice_channel is None:
            return MusicCommandResult(False, "你必須先加入一般語音頻道")

        player = get_player(self.bot, member.guild)
        if not self._can_move_player(member, player, voice_channel):
            return MusicCommandResult(
                False,
                "Bot 正在其他仍有聽眾的語音頻道播放；只有伺服器管理員可以移動 Bot",
            )

        url = url.strip()
        if not is_youtube_url(url):
            return MusicCommandResult(False, "僅支援 YouTube 或 YouTube Music 網址")

        if mode not in {"song", "playlist"}:
            return MusicCommandResult(False, "未知的播放模式")

        try:
            await player.connect(voice_channel)

            if mode == "playlist":
                songs, skipped = await player.add_playlist(
                    url,
                    requester=member,
                    channel=response_channel,
                )
                if not songs:
                    return MusicCommandResult(
                        False,
                        "播放清單為空或所有影片均無法播放",
                    )
                return MusicCommandResult(
                    True,
                    "播放清單已加入",
                    embed=playlist_added_embed(songs, skipped=skipped),
                )

            was_active = player.is_active
            song = await player.add_song(
                url,
                requester=member,
                channel=response_channel,
            )
        except (ConnectionError, QueueFullError) as exc:
            return MusicCommandResult(
                False,
                str(exc) or type(exc).__name__,
            )
        except Exception as exc:
            log.exception("[%s] 播放失敗", member.guild.name)
            return MusicCommandResult(
                False,
                str(exc) or type(exc).__name__,
            )

        if was_active:
            return MusicCommandResult(
                True,
                f"已加入播放佇列：{song.title}",
                embed=added_song_embed(song, player.queue.size),
                song=song,
            )

        return MusicCommandResult(
            True,
            f"正在播放：{song.title}",
            embed=now_playing_embed(song, player.queue),
            view=MusicControls(player),
            song=song,
            track_now_playing=True,
        )

    @staticmethod
    async def _send_play_response(
        followup,
        result: MusicCommandResult,
    ) -> discord.Message | None:
        """依播放結果回覆 Interaction，僅在有 View 時傳送 View。"""

        embed = result.embed or (
            info_embed(result.message)
            if result.success
            else error_embed(result.message)
        )
        kwargs: dict[str, object] = {
            "embed": embed,
            "wait": result.track_now_playing,
        }

        if result.view is not None:
            kwargs["view"] = result.view

        return await followup.send(**kwargs)

    # ── 共用暫停 Command ──────────────────────

    async def execute_pause(
        self,
        member: discord.Member,
    ) -> MusicCommandResult:
        """暫停目前播放器。"""

        player = get_player(
            self.bot,
            member.guild,
        )

        if not player.is_connected:
            return MusicCommandResult(
                success=False,
                message="Bot 目前不在語音頻道中",
            )

        if not self._can_control_player(
            member,
            player,
        ):
            return MusicCommandResult(
                success=False,
                message=(
                    "你必須和 Bot 在同一個語音頻道才能控制播放器"
                ),
            )

        if not player.is_active:
            return MusicCommandResult(
                success=False,
                message="目前沒有播放中的音樂",
            )

        if player.is_paused:
            return MusicCommandResult(
                success=False,
                message="目前已經暫停播放",
            )

        player.pause()

        return MusicCommandResult(
            success=True,
            message="已暫停播放",
        )

    # ── 共用繼續 Command ──────────────────────

    async def execute_resume(
        self,
        member: discord.Member,
    ) -> MusicCommandResult:
        """繼續目前暫停的播放器。"""

        player = get_player(
            self.bot,
            member.guild,
        )

        if not player.is_connected:
            return MusicCommandResult(
                success=False,
                message="Bot 目前不在語音頻道中",
            )

        if not self._can_control_player(
            member,
            player,
        ):
            return MusicCommandResult(
                success=False,
                message=(
                    "你必須和 Bot 在同一個語音頻道才能控制播放器"
                ),
            )

        if not player.is_paused:
            return MusicCommandResult(
                success=False,
                message="目前沒有暫停中的音樂",
            )

        player.resume()

        return MusicCommandResult(
            success=True,
            message="已繼續播放",
        )

    # ── 共用跳過 Command ──────────────────────

    async def execute_skip(
        self,
        member: discord.Member,
    ) -> MusicCommandResult:
        """跳過目前播放中的歌曲。"""

        player = get_player(
            self.bot,
            member.guild,
        )

        if not player.is_connected:
            return MusicCommandResult(
                success=False,
                message="Bot 目前不在語音頻道中",
            )

        if not self._can_control_player(
            member,
            player,
        ):
            return MusicCommandResult(
                success=False,
                message=(
                    "你必須和 Bot 在同一個語音頻道才能控制播放器"
                ),
            )

        if not player.is_active:
            return MusicCommandResult(
                success=False,
                message="目前沒有播放中的音樂",
            )

        player.skip()

        return MusicCommandResult(
            success=True,
            message="已跳過目前歌曲",
        )

    # ── 共用離開 Command ──────────────────────

    async def execute_leave(
        self,
        member: discord.Member,
    ) -> MusicCommandResult:
        """讓播放器離開目前語音頻道。"""

        player = get_player(
            self.bot,
            member.guild,
        )

        if not player.is_connected:
            return MusicCommandResult(
                success=False,
                message="Bot 目前不在語音頻道中",
            )

        if not self._can_control_player(
            member,
            player,
        ):
            return MusicCommandResult(
                success=False,
                message=(
                    "你必須和 Bot 在同一個語音頻道才能控制播放器"
                ),
            )

        await player.disconnect()

        return MusicCommandResult(
            success=True,
            message="已離開語音頻道",
        )

    # ── /play ──────────────────────

    @app_commands.command(
        name="play",
        description="播放 YouTube 音樂或歌單。",
    )
    @app_commands.describe(
        url="YouTube 單曲或播放清單 URL",
        mode="URL 類型，未選擇時預設為單曲",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="單曲", value="song"),
            app_commands.Choice(name="歌單", value="playlist"),
        ]
    )
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.guild_only()
    async def cmd_play(
        self,
        interaction: discord.Interaction,
        url: str,
        mode: str = "song",
    ) -> None:
        member = interaction.user
        response_channel = interaction.channel

        if not isinstance(member, discord.Member) or response_channel is None:
            await interaction.response.send_message(
                embed=error_embed("此指令僅限伺服器使用"),
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        result = await self.execute_play(
            member,
            response_channel,
            url,
            mode=mode,
        )

        message = await self._send_play_response(
            interaction.followup,
            result,
        )

        if (
            result.track_now_playing
            and result.song is not None
            and message is not None
        ):
            player = get_player(self.bot, member.guild)
            await player.set_now_playing_message(message, result.song)

    # ── /music ──────────────────────

    @app_commands.command(
        name="music",
        description="開啟音樂控制面板。",
    )
    @app_commands.allowed_installs(
        guilds=True,
        users=False,
    )
    @app_commands.guild_only()
    async def cmd_music(
        self,
        interaction: discord.Interaction,
    ) -> None:
        guild = interaction.guild

        if guild is None:
            await interaction.response.send_message(
                embed=error_embed(
                    "此指令僅限伺服器使用"
                ),
                ephemeral=True,
            )
            return

        player = get_player(
            self.bot,
            guild,
        )

        await interaction.response.send_message(
            embed=music_panel_embed(
                player
            ),
            view=MusicPanelView(
                self,
                interaction.user.id,
            ),
            ephemeral=True,
        )

    # ── $musicstatus ──────────────────────

    @commands.command(
        name="musicstatus",
        hidden=True,
    )
    @commands.is_owner()
    async def cmd_musicstatus(
        self,
        ctx: commands.Context,
    ) -> None:
        manager = get_manager()
        players = manager.all_players()

        active = [
            (guild_id, player)
            for guild_id, player in players.items()
            if player.is_active
        ]

        lines = [
            f"目前共在 **{len(active)}** 個伺服器播放音樂："
        ]

        for guild_id, player in active:
            guild = self.bot.get_guild(
                guild_id
            )

            name = (
                guild.name
                if guild
                else f"Guild {guild_id}"
            )

            song = player.current_song

            lines.append(
                f"  - **{name}**："
                f"{song.title if song else '無'}"
                f"  （佇列 {player.queue.size} 首）"
            )

        await ctx.reply(
            embed=info_embed(
                "\n".join(lines)
            )
        )

    # ── 事件監聽 ──────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """
        處理播放器語音狀態。

        Bot 被強制移出語音頻道時清理播放器；
        頻道只剩 Bot 時啟動播放器閒置計時器。
        """

        if (
            member == self.bot.user
            and after.channel is None
        ):
            player = get_player(
                self.bot,
                member.guild,
            )

            await player.disconnect()
            return

        voice_client = member.guild.voice_client

        if (
            voice_client
            and before.channel
            and before.channel.id
            == voice_client.channel.id
        ):
            human_members = [
                voice_member
                for voice_member
                in voice_client.channel.members
                if not voice_member.bot
            ]

            if not human_members:
                get_player(
                    self.bot,
                    member.guild,
                )._start_idle_timer()

    @commands.Cog.listener()
    async def on_guild_remove(
        self,
        guild: discord.Guild,
    ) -> None:
        """Bot 離開伺服器時清理播放器實例。"""

        remove_player(
            guild.id
        )

        log.info(
            "Guild %d（%s）的播放器已清除",
            guild.id,
            guild.name,
        )
