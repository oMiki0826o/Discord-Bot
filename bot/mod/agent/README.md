# Agent Feature Module

`agent/` 是可選的進階 AI 執行模組，正式位置為 `bot/mod/agent/`。它宣告
`MODULE_DEPENDENCIES = ("ai",)`，並只透過 `bot.mod.ai.api` 取得基礎 AI 能力。

## 安裝與行為

1. 先安裝完整的 `ai/` Module。
2. 將本目錄複製為 `bot/mod/agent/`。
3. ModuleLoader 會先載入 `ai`，再載入 `agent`。
4. Extension 會建立 `settings/agent.json`，但不建立資料庫、Cog 或 Provider client。

載入後，Agent 取代 AI 的 active runtime；卸載後立即回復 `BasicRuntime`，
`@Bot` 與 `/ai` 仍可正常使用。AI reload 時，Agent factory 會以新的 AI services
重建 runtime，不保留舊 Provider 或 DB reference。

## 提供的能力

- Function Calling 與有限多回合 Tool Loop。
- Tool capability、argument schema、timeout 與數量限制。
- Duplicate Tool Call 防護與強制收尾。
- Skill metadata 先列出，需要時才讀取完整 `SKILL.md`。
- Read-only Agent 失敗時最多降級重試一次 BasicRuntime。

## 工具與權限

內建工具全部只讀：

- `search_user_memory`：只查發起者的 private memory。
- `search_history`：發起者與當前頻道的 History。
- `read_topics`：發起者與當前頻道的 Topic State。
- `read_public_profile` / `search_public_profiles`：可查他人，但只讀明確公開欄位。
- `search_knowledge` / `read_knowledge_chunk`：Owner 索引的 Knowledge。
- `read_channel_context`：只讀當前頻道，並由 AI adapter 檢查 Discord 權限。
- `list_skills` / `read_skill`：只讀 `agent/resources/skills/`。

模型不能指定 private `user_id` 或 `channel_id`，也無法存取 SQLite connection、
Discord Client、任意檔案路徑、Shell、API key、token 或其他 Feature Module。

## Settings

`settings/agent.json` 只含 Agent-owned budget：

- `max_model_turns`
- `max_tool_calls`
- `total_timeout_seconds`
- `tool_timeout_seconds`

AI Provider、Memory、Prompt、Context 與 Attachment 設定仍屬於 `settings/ai.json`。
