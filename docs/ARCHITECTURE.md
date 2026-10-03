# 架構導覽

這份文件說明專案的執行邊界、模組生命週期與資料位置，方便第一次閱讀原始碼的人快速找到正確入口。

## 啟動流程

```text
main.py
  └─ bot/startup.py
      ├─ 驗證 .env
      ├─ 建立 data/ 與日誌目錄
      ├─ 載入 Core Settings
      ├─ 建立 DiscordBot
      ├─ 建立 ModuleLoader
      ├─ 載入 bot/mod/*/extension.py
      └─ 同步 Slash Command 並開始接收 Discord 事件
```

`main.py` 是唯一程式入口。Application 組裝與安全關閉由 `bot/startup.py` 管理；Discord Client 本身則位於 `bot/core/discord/client.py`。

## Core 與 Module 邊界

```text
bot/
├─ core/     共用基礎能力
└─ mod/      功能模組
```

依賴方向固定為 **Module → Core**。Core 不應 import `bot.mod.*`，功能模組也不應直接 import 其他模組的內部實作。需要跨模組合作時，應透過明確的 public facade 或 Module dependency，例如 `agent` 宣告依賴 `ai`，再使用 `bot.mod.ai.api`。

Core 目前提供：

- Discord Client、Intents、Presence、Owner resolution。
- Prefix／Slash Command 的共用處理。
- JSON Settings 與 schema/migration。
- SQLite 共用連線與 migration 基礎設施。
- Logging、Discord error reporting 與 session report。
- Module discovery、dependency graph 與 lifecycle。
- 共用自然語言快捷指令 registry。

## Module 載入與依賴

模組入口固定為：

```text
bot/mod/<module>/extension.py
```

Extension 可宣告：

```python
MODULE_VERSION = "0.1.0"
MODULE_DISPLAY_NAME = "Example"
MODULE_DEPENDENCIES = ("ai",)
```

ModuleLoader 先以 AST 讀取 metadata，不需要為了掃描模組而 import 功能程式碼。載入時會驗證依賴圖並依拓樸順序啟動；關閉時則反向卸載。

`settings/modules.json` 的 `required` 代表 Application 必須具備的模組。必要模組若不存在、載入失敗或被設定為 disabled，啟動會明確失敗，不會以缺功能的狀態假裝正常運行。預設必要模組為 `basic` 與 `system`。

## Settings 與 Secret

兩類設定必須分開：

- `.env`：`DISCORD_TOKEN`、`OWNER_ID`、`GEMINI_API` 等部署資訊或 Secret。
- `settings/*.json`：可公開的功能設定。

模組在 `setup()` 內呼叫 `settings.register(...)` 註冊預設值、schema version 與驗證規則。設定檔不存在時會自動建立；既有設定會補上缺少欄位並在需要時執行 migration。

`settings/*.json` 是部署端狀態，預設不納入 Git 或正式發布 ZIP。Secret 不應寫入 JSON、原始碼、README、log 或錯誤訊息。

## Runtime 資料與 SQLite

執行期間產生的內容集中在 `data/`：

```text
data/
├─ database/    模組 SQLite
├─ logs/        Session log
├─ backups/     Settings / migration 備份
└─ <module>/    模組自己的 runtime data
```

資料表語意由各模組自行擁有；Core 只提供連線與 migration 基礎設施。SQLite 工作應保持短生命週期。大量掃描、文件轉換或其他可能阻塞事件迴圈的工作，應交給背景 task 或 `asyncio.to_thread()`。

AI 記憶另外刻意拆成兩個 JSON 表面：`data/ai/users_memory/` 是 Owner 手動維護的記憶原稿；`data/ai/auto_memory/` 是自主記憶的可編輯鏡像。兩者 schema 與同步方向不同，不可共用同一目錄；Runtime 的自主記憶查詢仍以 SQLite 為權威來源。

## Discord 入口

一般使用者主要透過 Slash Command、Button、Select 與 Modal 操作。Owner 維運使用 Prefix Command，預設前綴為 `$`。

`/help` 依目前實際載入的模組建立內容，因此不需要維護另一份容易過期的靜態指令清單。

部分模組可向 Core 的 natural-command registry 註冊固定句型。Core 只負責比對與分派，真正的操作仍留在功能模組中。

## 背景工作與關閉

建立背景 task 的元件必須提供對應的停止流程，例如：

- Guild statistics worker。
- Announcement scheduler。
- AI memory worker / memory mirror watcher。
- Music idle / voice watchdog。

Extension unload 或 Cog unload 應先停止背景工作，再釋放播放器、Provider client、View 或其他外部資源。Application 關閉時，`startup.py` 會先卸載模組，再傳送 session report，最後關閉 Discord Client。
