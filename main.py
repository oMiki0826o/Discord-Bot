"""
main.py

Modification():

- 提供 Discord Bot 唯一程式入口。
- 將 Bot 啟動流程交由 bot.startup 管理。

本檔為專案唯一的程式執行入口。
"""

from __future__ import annotations

from bot.startup import run


# ── 執行入口 ──────────────────────

if __name__ == "__main__":
    run()