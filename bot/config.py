"""
bot/config.py

Modification():

- 統一管理專案基礎路徑。
- 統一管理功能模組路徑與 Python Package。
- 統一管理 Runtime 資料與資料庫目錄。
- 統一載入 .env 環境變數。
- 提供 Discord 與 Owner Application 級設定。
- 驗證 Bot 啟動所需的必要環境變數。

本檔只負責環境變數與專案基礎路徑，
不執行 Runtime 初始化或功能模組設定。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


# ── 專案路徑 ──────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent

BOT_DIR = PROJECT_ROOT / "bot"

MODULES_DIR = BOT_DIR / "mod"

SETTINGS_DIR = PROJECT_ROOT / "settings"

DATA_DIR = PROJECT_ROOT / "data"

DATABASE_DIR = DATA_DIR / "database"

LOG_DIR = DATA_DIR / "logs"

ENV_FILE = PROJECT_ROOT / ".env"


# ── Python Package ──────────────────────

MODULES_PACKAGE = "bot.mod"


# ── 環境變數載入 ──────────────────────

load_dotenv(ENV_FILE)


def _get_env(
    name: str,
    default: str = "",
) -> str:
    """讀取並清理環境變數。"""

    return os.getenv(
        name,
        default,
    ).strip()


def _get_optional_int(
    name: str,
) -> int | None:
    """讀取可選的整數環境變數。"""

    value = _get_env(name)

    if not value:
        return None

    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(
            f"環境變數 {name} 必須是整數。"
        ) from exc


# ── Discord ──────────────────────

DISCORD_TOKEN = _get_env(
    "DISCORD_TOKEN"
)

OWNER_ID = _get_optional_int(
    "OWNER_ID"
)


# ── 設定驗證 ──────────────────────

def validate_config() -> None:
    """驗證 Bot 啟動所需的必要環境設定。"""

    if not DISCORD_TOKEN:
        raise RuntimeError(
            "缺少 DISCORD_TOKEN，請檢查專案根目錄的 .env。"
        )
