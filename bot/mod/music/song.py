"""
bot/mod/music/song.py

Modification():

- 定義音樂資料模型與音訊來源。
- 解析單曲、播放清單與搜尋關鍵字。
- 在背景執行緒處理 yt-dlp 操作。
- 將播放用串流來源於實際播放前建立。

本檔負責 Music Module 的歌曲資料與來源解析。
"""

from __future__ import annotations

import asyncio
import logging
import re
import shlex
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import discord
import yt_dlp

from bot.mod.music.url import is_youtube_url
from bot.mod.music.config import get, get_int

log = logging.getLogger("bot.music.song")

# ── ANSI 代碼清除 ──────────────────────

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """移除 yt-dlp 錯誤訊息中的 ANSI 顏色代碼，避免在 Discord 顯示亂碼。"""
    return _ANSI_RE.sub("", text)


# ── 查詢字串正規化 ──────────────────────

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _search_prefix() -> str:
    """
    從 settings 讀取搜尋前綴，預設為 ytsearch。

    設為可調整值而非寫死字串，讓未來若想改為 ytsearch5（取前 5 筆
    結果供使用者選擇）等變體行為時，不需修改程式碼即可切換。
    """
    return get("music.search_prefix", "ytsearch")


def _normalize_query(query: str) -> str:
    """
    確保非網址的查詢字串一定會被當作搜尋關鍵字處理。

    不依賴 yt-dlp 對「輸入是否像網址」的內部判斷（該判斷對含冒號的
    純文字查詢不可靠，見檔案頂部說明），改為我們自行判斷：
    以 http:// 或 https:// 開頭才視為網址原樣傳入，其餘一律加上
    搜尋前綴，確保 yt-dlp 一定會走搜尋路徑而非誤判為未知 scheme。
    """
    cleaned = query.strip()
    if _URL_RE.match(cleaned):
        return cleaned
    return f"{_search_prefix()}:{cleaned}"


# ── YT-DLP 配置 ──────────────────────

_YTDL_BASE: dict[str, Any] = {
    "format":         "bestaudio/best",
    "quiet":          True,
    "no_warnings":    True,
    "default_search": "ytsearch",  # 第二層防護；實際判斷已由 _normalize_query() 處理
    "source_address": "0.0.0.0",
    "retries":        3,
    "fragment_retries": 3,
}

# YoutubeDL 會在擷取期間暫存狀態，不共用實例，避免多個 Guild
# 同時點歌時互相污染 extractor 狀態。
_YTDL_SINGLE_OPTIONS = {**_YTDL_BASE, "noplaylist": True}
_YTDL_PLAYLIST_OPTIONS = {
    **_YTDL_BASE,
    "noplaylist": False,
    "ignoreerrors": True,
}


# ── FFmpeg 配置 ──────────────────────

_FORWARDED_HEADER_NAMES = {
    "accept",
    "accept-language",
    "cookie",
    "origin",
    "referer",
    "user-agent",
}


def _ffmpeg_opts(http_headers: dict[str, Any] | None = None) -> dict[str, str]:
    """組裝 FFmpeg 選項，並傳遞 yt-dlp 產生串流 URL 時使用的 headers。"""
    before = (
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_delay_max 5"
    )
    forwarded: list[str] = []
    for raw_name, raw_value in (http_headers or {}).items():
        name = str(raw_name).strip()
        value = str(raw_value).replace("\r", "").replace("\n", "").strip()
        if name.lower() in _FORWARDED_HEADER_NAMES and value:
            forwarded.append(f"{name}: {value}\r\n")
    if forwarded:
        before += f" -headers {shlex.quote(''.join(forwarded))}"

    return {
        "executable":     get("music.ffmpeg_path", "ffmpeg"),
        "before_options": before,
        "options": "-vn",
    }


# ── 工具函式 ──────────────────────

def _extract(options: dict[str, Any], query: str) -> dict[str, Any]:
    """使用獨立 YoutubeDL 實例同步提取，供 executor 使用。"""
    with yt_dlp.YoutubeDL(options) as ytdl:
        return ytdl.extract_info(query, download=False)


def _build_song(data: dict[str, Any], requester: discord.Member) -> "Song":
    """從 yt-dlp 資料字典建立 Song 物件。"""
    return Song(
        title       = data.get("title", "未知標題"),
        webpage_url = data.get("webpage_url") or data.get("url", ""),
        uploader    = data.get("uploader") or data.get("channel", ""),
        duration    = int(data.get("duration") or 0),
        thumbnail   = data.get("thumbnail"),
        requester   = requester,
    )


def format_duration(seconds: int) -> str:
    """將秒數格式化為 MM:SS 或 HH:MM:SS。"""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


# ── Song 資料模型 ──────────────────────

@dataclass
class Song:
    """
    單首歌曲的不可變資料容器。
    串流網址不在此儲存，由 create_source() 播放前即時提取。
    """

    title:       str
    webpage_url: str
    uploader:    str
    duration:    int
    thumbnail:   str | None
    requester:   discord.Member
    queue_id:     str = field(default_factory=lambda: uuid4().hex)

    @property
    def duration_str(self) -> str:
        return format_duration(self.duration)

    # ── 工廠：單曲 ──────────────────────

    @classmethod
    async def from_query(cls, query: str, requester: discord.Member) -> "Song":
        """
        從搜尋關鍵字或網址建立 Song。

        query 在送入 yt-dlp 前會先經過 _normalize_query() 正規化，
        非網址一律轉換為明確的搜尋語法，避免含冒號的查詢字串被
        誤判為未知 scheme 的網址。
        """
        if _URL_RE.match(query.strip()) and not is_youtube_url(query):
            raise ValueError("僅支援 YouTube 或 YouTube Music 網址")

        normalized = _normalize_query(query)
        loop = asyncio.get_event_loop()
        try:
            data: dict[str, Any] = await loop.run_in_executor(
                None, _extract, _YTDL_SINGLE_OPTIONS, normalized,
            )
        except Exception as exc:
            raise ValueError(_strip_ansi(str(exc))) from exc
        if "entries" in data:
            data = data["entries"][0]
        return _build_song(data, requester)

    # ── 工廠：播放清單 ──────────────────────

    @classmethod
    async def from_playlist(
        cls,
        url:       str,
        requester: discord.Member,
    ) -> tuple[list["Song"], int]:
        """
        解析 YouTube 播放清單，回傳 (成功歌曲清單, 跳過數量)。

        與 from_query 不同，這裡不會把非網址輸入轉換成搜尋語法：
        /play 的歌單模式就是要求提供播放清單網址，若輸入不是
        合法網址，直接回傳明確錯誤，避免產生語意不清的搜尋結果，
        也避免同樣落入 generic extractor 誤判 scheme 的情況。

        ignoreerrors=True 使 yt-dlp 遇到版權封鎖、私人影片或地區限制的
        影片時不拋出例外，而是在 entries 中回傳 None。
        此處過濾 None 並計算跳過數量，讓呼叫端可告知使用者詳情。
        """
        if not is_youtube_url(url):
            raise ValueError("請提供有效的 YouTube 或 YouTube Music 播放清單網址")

        limit = get_int("music.max_queue_size", 50)
        loop  = asyncio.get_event_loop()
        try:
            data: dict[str, Any] = await loop.run_in_executor(
                None, _extract, _YTDL_PLAYLIST_OPTIONS, url,
            )
        except Exception as exc:
            raise ValueError(_strip_ansi(str(exc))) from exc

        raw_entries = data.get("entries", [data])[:limit]
        songs:   list[Song] = []
        skipped: int        = 0

        for entry in raw_entries:
            if not entry:
                skipped += 1
                continue
            try:
                songs.append(_build_song(entry, requester))
            except Exception as exc:
                log.warning("跳過無效播放清單項目：%s", exc)
                skipped += 1

        return songs, skipped

    # ── 音訊來源 ──────────────────────

    async def create_source(self) -> discord.FFmpegPCMAudio:
        """
        播放前即時提取最新串流網址，建立 FFmpeg 音訊來源。

        self.webpage_url 來自 yt-dlp 回傳的 webpage_url 欄位，
        必為合法網址，不需經過 _normalize_query() 處理。
        """
        loop = asyncio.get_event_loop()
        try:
            data: dict[str, Any] = await loop.run_in_executor(
                None, _extract, _YTDL_SINGLE_OPTIONS, self.webpage_url,
            )
        except Exception as exc:
            raise ValueError(_strip_ansi(str(exc))) from exc
        if "entries" in data:
            data = data["entries"][0]
        stream_url = data.get("url")
        if not stream_url:
            raise ValueError("yt-dlp 未回傳可播放的音訊串流")

        parsed = urlparse(stream_url)
        client = parse_qs(parsed.query).get("c", [""])[0]
        headers = data.get("http_headers")
        log.info(
            "[stream] song=%s format=%s protocol=%s host=%s client=%s headers=%s",
            self.queue_id,
            data.get("format_id", "unknown"),
            data.get("protocol", "unknown"),
            parsed.hostname or "unknown",
            client or "default",
            sorted(str(name).lower() for name in headers) if isinstance(headers, dict) else [],
        )

        opts = _ffmpeg_opts(headers if isinstance(headers, dict) else None)
        exe  = opts.pop("executable", "ffmpeg")
        return discord.FFmpegPCMAudio(stream_url, executable=exe, **opts)
