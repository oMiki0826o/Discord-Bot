"""
tests/test_help_ui.py

Modification():

- 驗證 Help 分頁切割與中文分類名稱。
- 驗證 Help View 保存原始操作使用者。

本檔檢查 Help 介面的基本呈現資料。
"""

from __future__ import annotations

import pytest

discord = pytest.importorskip("discord")

from bot.mod.basic.help.command import _build_categories, _format_category_name
from bot.mod.basic.help.models import HelpEntry
from bot.mod.basic.help.view import HelpView


def test_help_category_translation() -> None:
    assert _format_category_name("basic") == "基本功能"
    assert _format_category_name("moderation") == "伺服器管理"
    assert _format_category_name("voice") == "語音頻道"


def test_help_pages_split_and_bind_owner() -> None:
    categories = _build_categories({
        "basic": [HelpEntry(name=f"command-{index}", description="測試") for index in range(7)]
    })
    assert len(categories) == 1
    assert len(categories[0].pages) == 2
    view = HelpView(categories, user_id=123)
    assert view.user_id == 123
    assert len(view.category_select.options) == 1
