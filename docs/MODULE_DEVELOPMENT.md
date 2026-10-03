# 模組開發教學

Module 是可獨立載入的功能單位。小功能可以只有 `extension.py` 與一個 Cog；只有在設定、資料、服務或 UI 真的變複雜後才拆檔，不需要為了目錄外觀建立空層級。

## 最小模組

```text
bot/mod/example/
├─ __init__.py
└─ extension.py
```

`extension.py`：

```python
from discord.ext import commands

MODULE_VERSION = "0.1.0"
MODULE_DISPLAY_NAME = "Example"
MODULE_DEPENDENCIES: tuple[str, ...] = ()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ExampleCog())


async def teardown(bot: commands.Bot) -> None:
    return None
```

`MODULE_DEPENDENCIES` 只宣告真正的功能依賴。不要用跨 Module import 取代 dependency contract；需要跨模組能力時，依賴方應使用對方明確公開的 facade。

常見模組結構：

```text
bot/mod/example/
├─ extension.py       組裝與生命週期
├─ config.py          預設設定與 schema
├─ command.py         Cog / Slash Command / event 入口
├─ service.py         業務邏輯
├─ database.py        schema / repository
└─ views.py           Button / Select / Modal
```

## Settings

模組在 `setup()` 期間註冊自己的設定：

```python
from bot.core.settings.manager import settings
from bot.core.settings.schema import SettingRule

SETTINGS_NAME = "example"
DEFAULT_SETTINGS = {"timeout_seconds": 60}
SETTINGS_SCHEMA = {
    "timeout_seconds": SettingRule(int, minimum=5, maximum=600),
}

configuration = settings.register(
    SETTINGS_NAME,
    DEFAULT_SETTINGS,
    SETTINGS_SCHEMA,
)
```

第一次載入會建立 `settings/example.json`。Token、API Key 等機密資料必須留在 `.env`，不要放入一般 Settings。

## Database

資料應由使用它的 Module 自己擁有：

```python
from pathlib import Path

from bot.core.database.sqlite import connect, initialize


class ExampleDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        initialize(path)
        with connect(path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS example_items "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
```

不要在 import 時建立資料庫或啟動背景工作；這些副作用應在 `setup()` / service lifecycle 發生。會做大量檔案或資料掃描的同步工作，要避免直接卡住 Discord event loop。

## 自然語言快捷指令

Core registry 可以處理固定句型，例如：

```python
from bot.core.discord.natural_command import NaturalCommand, natural_commands

OWNER = "example"


async def play(message, arguments: dict[str, str]) -> None:
    await message.reply(f"準備播放：{arguments['url']}")


async def setup(bot) -> None:
    natural_commands.register_many(
        OWNER,
        (NaturalCommand(pattern="播放 {url}", handler=play),),
    )


async def teardown(bot) -> None:
    natural_commands.unregister(OWNER)
```

Reload 前必須解除註冊，否則舊 handler 可能殘留並造成重複執行。

## Discord 權限

`app_commands.default_permissions(...)` 只代表 Discord UI 的預設權限。敏感操作仍應加入執行期 `app_commands.checks.has_permissions(...)` 或等價檢查。

Guild-only command 也應限制 installation scope，避免變成使用者安裝指令。

## setup / teardown

`setup()` 負責組裝：

- 註冊 Settings。
- 初始化模組自有資料。
- 建立 service / worker。
- 加入 Cog。
- 註冊 handler / natural command。

若 setup 中途失敗，應回滾已建立的 runtime 資源後再重新拋出例外。

`teardown()` 則反向清理：先停止背景 task，再解除 handler、播放器、Provider、外部連線等資源。只有 Cog 本身的資源，也可以在 `cog_unload()` 中處理。

## 測試

至少執行：

```bash
python -m pytest -q
python -m compileall -q bot tests
```

最後再到測試伺服器檢查 Slash Command、權限邊界、View timeout、Module reload，以及任何 Voice 或外部 API 流程。
