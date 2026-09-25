"""
bot/core/logging/constants.py

Modification():

- 定義 Logging Session 與 Log 檔案路徑。
- 定義 Logging 輸出格式。
- 定義 Log Rotation 大小限制。
- 定義 Discord 訊息與 Log 上傳限制。
- 定義 Logging Settings 共用路徑。

本檔只定義 Logging 系統使用的常數。
"""

from __future__ import annotations

from datetime import datetime

from bot.config import LOG_DIR


# ── Session ──────────────────────

_SESSION_TIME = datetime.now()

SESSION_DATE = _SESSION_TIME.strftime("%Y-%m-%d")
SESSION_TIME = _SESSION_TIME.strftime("%H-%M-%S")


# ── Log 路徑 ──────────────────────

SESSION_LOG_DIR = LOG_DIR / SESSION_DATE

LOG_FILE = (
    SESSION_LOG_DIR
    / f"bot_{SESSION_DATE}_{SESSION_TIME}.log"
)


# ── Log 格式 ──────────────────────

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# ── Log Rotation ──────────────────────

LOG_ROTATE_MAX_BYTES = 20 * 1024 * 1024
LOG_ROTATE_BACKUP_COUNT = 5


# ── Discord ──────────────────────

DISCORD_MESSAGE_LIMIT = 2000
TRACEBACK_CHUNK_SIZE = 1900
LOG_UPLOAD_MAX_BYTES = 7 * 1024 * 1024


# ── Settings Paths ──────────────────────

ERROR_REPORTING_ENABLED = (
    "logging.error_reporting.enabled"
)

ERROR_REPORTING_FULL_CONTEXT = (
    "logging.error_reporting.full_context"
)

ERROR_REPORTING_DESTINATION = (
    "logging.error_reporting.destination"
)

ERROR_REPORTING_CHANNEL_ID = (
    "logging.error_reporting.channel_id"
)

SHUTDOWN_REPORT_SEND_LOG_FILE = (
    "logging.shutdown_report.send_log_file"
)