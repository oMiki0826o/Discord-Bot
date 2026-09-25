# 模組開發

## 最小結構

```text
bot/mod/example/
├── __init__.py
└── extension.py
```

`extension.py` 是 discord.py Extension 的入口：

```python
from discord.ext import commands

MODULE_VERSION = "1.0.0"
MODULE_DEPENDENCIES = ()


async def setup(bot: commands.Bot) -> None:
    ...


async def teardown(bot: commands.Bot) -> None:
    ...
```

小型模組可以只保留 `extension.py`；功能變大後再依職責拆分，不必一開始就建立大量空檔案。

## 常見檔案配置

```text
bot/mod/example/
├── __init__.py
├── extension.py
├── config.py
├── command.py
├── service.py
├── database.py
└── views.py
```

- `extension.py`：組裝與生命週期。
- `config.py`：預設設定、Schema 與讀取介面。
- `command.py`：Discord 指令與事件入口。
- `service.py`：主要業務邏輯。
- `database.py`：持久化資料。
- `views.py`：Button、Select、Modal 等互動元件。

依實際需求拆分即可，不需要為了符合目錄範例而建立空模組。

## 模組依賴

有前置需求時，在 `extension.py` 宣告：

```python
MODULE_DEPENDENCIES = ("basic", "other_module")
```

載入器會先載入依賴。缺少依賴、依賴被停用、自我依賴或循環依賴都會在載入階段被攔下。

只有真的存在模組間依賴時才宣告，不需要把所有模組都綁在一起。

## Settings

模組可在 `config.py` 定義預設值與 Schema，例如：

```python
from bot.core.settings.schema import SettingRule

DEFAULT_SETTINGS = {
    "timeout_seconds": 60,
}

SETTINGS_SCHEMA = {
    "timeout_seconds": SettingRule(int, minimum=5, maximum=600),
}
```

Settings Manager 會補上缺少欄位並驗證既有值。設定錯誤應在載入時就清楚回報，而不是等到使用功能時才失敗。

## Database

資料屬於哪個功能，就由該模組負責。資料庫初始化放在 `setup()` 階段，避免 import 檔案時就產生連線或建立檔案。

同步 SQLite 操作若可能阻塞 Event Loop，可使用 `asyncio.to_thread()`；交易保持短小，並確保錯誤時能 rollback。

## Discord 指令與 UI

Slash Command 的 `description` 是使用者會直接看到的文字，保持簡短、自然、一致。管理功能除了 `default_permissions` 之外，也要有執行期的權限檢查。

互動面板若屬於單一使用者的操作流程，應在 `interaction_check()` 限制操作人；有 timeout 的 View 在逾時後停用按鈕或選單，避免留下失效介面。

## setup 與 teardown

`setup()` 只負責組裝：

1. 註冊設定。
2. 初始化資料庫或服務。
3. 建立 Cog／View／Handler。
4. 將資源掛到 Bot 或模組容器。

`teardown()` 反向清理：

1. 停止背景 Task。
2. 解除 Handler 或 Persistent View。
3. 關閉播放器、連線或其他外部資源。
4. 移除暫存狀態。

如果 `setup()` 做到一半失敗，應盡可能回滾已建立的資源再把錯誤往上拋。

## 測試

至少為容易回歸的純邏輯加入離線測試，例如：

- 設定 Schema。
- 模組依賴圖。
- 權限裝飾器。
- 分頁與格式化。
- Queue／Repository 的純邏輯。

與 Discord API、Voice、FFmpeg 或網路相關的功能仍需實際環境驗收。
