# 架構說明

這份文件用來快速理解專案怎麼啟動、功能放在哪裡，以及模組與 Core 之間如何合作。

## 整體結構

```text
main.py
  └─ bot/startup.py
      ├─ bot/core/
      │   ├─ discord/
      │   ├─ modules/
      │   ├─ settings/
      │   ├─ database/
      │   └─ logging/
      └─ bot/mod/
          ├─ basic/
          ├─ guild/
          ├─ music/
          ├─ ticket/
          └─ ...
```

`main.py` 保持很薄，只負責進入啟動流程。`bot/startup.py` 組裝 Discord Client、設定、日誌與模組載入器；實際功能則放在 `bot/mod/`。

## 啟動流程

```text
python main.py
    ↓
讀取環境變數與設定
    ↓
建立 Runtime 目錄與 Logging
    ↓
建立 DiscordBot
    ↓
發現並載入功能模組
    ↓
同步 Slash Command
    ↓
進入正常執行
```

啟動失敗時，優先查看終端與 `data/logs/`。必要模組由 `settings/modules.json` 的 `required` 決定；必要模組失敗會中止啟動，其餘模組則會留下錯誤狀態供管理介面查看。

## Core

`bot/core/` 保存跨功能共用的基礎能力。

- `discord/`：Client、Intent、Prefix、全域指令錯誤處理與自然語言快捷指令。
- `modules/`：模組發現、依賴驗證、載入、卸載與狀態管理。
- `settings/`：JSON 設定載入、預設值合併與 Schema 驗證。
- `database/`：SQLite 與 migration 共用工具。
- `logging/`：Console、檔案日誌與 Discord 錯誤通報。

功能模組可以依賴 Core；Core 不反過來依賴某個特定功能模組。

## 功能模組

可載入模組位於：

```text
bot/mod/<module>/extension.py
```

`extension.py` 可宣告：

```python
MODULE_VERSION = "1.0.0"
MODULE_DEPENDENCIES = ("basic",)
```

`MODULE_DEPENDENCIES` 是選用欄位。模組有前置需求時直接宣告即可，載入器會先處理依賴，再載入目前模組。它同時會檢查：

- 找不到的依賴。
- 已停用的必要依賴。
- 模組依賴自己。
- 循環依賴。

批次卸載則採相反順序，避免先拆掉仍被其他模組使用的前置模組。

## Settings

公開設定位於：

```text
settings/<name>.json
```

各模組在載入時註冊預設值與必要的 `SETTINGS_SCHEMA`。Settings Manager 會保留既有值、補上缺少的新欄位，並在使用設定前檢查型別、範圍與允許值。

敏感資訊使用 `.env`，不放入 JSON。

## Database

需要持久化資料的功能各自管理自己的資料。SQLite 檔案預設放在 `data/database/`，Core 僅提供連線與 migration 的共用能力。

Discord Event Loop 不適合被長時間阻塞；較重的同步 SQLite 工作應在背景執行緒完成，交易本身則保持短小。

## Discord UI 與指令

一般使用者以 Slash Command 與互動面板為主；Owner 的系統維護功能使用 Prefix Command。面板會盡量限制由原操作人繼續操作，逾時後停用互動元件，避免留下看似可按但已失效的介面。

`bot/core/discord/natural_command.py` 提供簡單文字匹配，可讓 Music、Voice 等模組註冊快捷指令。它只負責比對與分派，實際邏輯仍由各功能模組處理。

## 關閉流程

```text
收到關閉要求
    ↓
卸載功能模組
    ↓
整理關閉報告與日誌
    ↓
關閉 Discord Client
```

持有播放器、背景 Task、Persistent View 或其他資源的模組，應在 `teardown()` 釋放。

## Runtime Data

執行期間會產生：

```text
.env
data/
*.db
*.log
__pycache__/
```

這些內容不屬於原始碼，也不應進入發布包或版本控制。
