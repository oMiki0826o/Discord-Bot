# Discord Bot

![Version](https://img.shields.io/badge/version-v0.1.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tech](https://img.shields.io/badge/stack-Python%20%2B%20discord.py-lightgrey)
![Python](https://img.shields.io/badge/Python-3.11%2B-orange)

[中文](#中文) | [English](#english)

---

## 中文

### 目錄

- [關於](#關於)
- [功能](#功能)
- [安裝](#安裝)
- [使用方式](#使用方式)
- [授權](#授權)

### 關於

Discord Bot 是以 Python 與 `discord.py` 開發的模組化 Discord Bot, 整合伺服器管理, 音樂播放, 身分組面板, 工單, Join-to-Create 臨時語音頻道, 訊息工具與文件轉換等常用功能.

專案將 Discord 事件與功能拆分為獨立 Module, 並由 Core 統一處理模組生命週期, 設定, SQLite 資料庫, 日誌與錯誤通報. Module Loader 支援前置依賴檢查與載入排序, 讓各項功能可以獨立維護, 也方便後續擴充.

日常操作以 Slash Command 與互動面板為主, Owner 管理功能則提供模組管理, 設定重新載入, 指令同步, Discord 狀態調整與安全關閉等維運入口.

### 功能

- 伺服器工具: 歡迎與離開訊息, 自動身分組, 伺服器設定與基本資訊.
- 管理功能: 警告, 禁言, 管理紀錄與權限檢查.
- 音樂播放: YouTube 搜尋與播放, 播放清單, 佇列, 收藏, 循環, 音量與互動控制面板.
- 社群功能: 自助身分組面板, 工單系統與 Join-to-Create 臨時語音頻道.
- 訊息與文件工具: 一般訊息, Embed, Webhook 發送, 以及透過 `/markitdown` 轉換常見文件格式.
- 維運工具: Module 載入與重新載入, Slash Command 同步, Settings 驗證, 日誌, 錯誤通報與 Owner 控制面板.

### 安裝

需求:

- Python 3.11 或以上.
- Discord Bot Token.
- FFmpeg, 使用音樂播放功能時需要.
- 可正常連線至 Discord 與 YouTube 的網路環境.

下載專案並建立虛擬環境:

```bash
git clone https://github.com/oMiki0826o/discord-bot.git
cd discord-bot
python3.11 -m venv .venv
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

安裝依賴:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

若要使用發布時驗證過的固定依賴版本, 可改用:

```bash
python -m pip install -r requirements-lock.txt
```

複製環境變數範例:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

接著編輯 `.env`:

```env
DISCORD_TOKEN=你的_Discord_Bot_Token
OWNER_ID=你的_Discord_使用者_ID
```

`DISCORD_TOKEN` 用於 Bot 登入. `OWNER_ID` 用於 Owner 管理指令. 其他可公開調整的功能設定集中在 `settings/`.

### 使用方式

在 Discord Developer Portal 建立 Bot 後, 請依實際使用的功能開啟需要的 Privileged Gateway Intents, 並以包含 `bot` 與 `applications.commands` Scope 的邀請連結加入伺服器. 權限建議依啟用功能個別授予, 不需要為了方便直接開啟 Administrator.

啟動 Bot:

```bash
python main.py
```

啟動後可先使用:

```text
/help
/ping
/botinfo
```

`/help` 會依目前實際載入的 Module 顯示可用指令. 音樂, 工單, 身分組與語音頻道等功能也會透過各自的 Slash Command 與互動面板操作.

Owner 指令預設使用 `$` Prefix. 常用入口如下:

```text
$help
$bot
$mod
$settings
$slash
$presence
$error
```

需要停止 Bot 時可使用:

```text
$bot stop
```

執行期間產生的 SQLite 資料庫與日誌集中在 `data/`. 架構, 開發方式與 Module 實作細節可參考 [架構說明](./docs/ARCHITECTURE.md), [開發指南](./docs/DEVELOPMENT.md) 與 [模組開發](./docs/MODULE_DEVELOPMENT.md).

### 授權

本專案採用 MIT License 授權, 詳見 [LICENSE](./LICENSE).

---

## English

### Table of Contents

- [About](#about)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [License](#license)

### About

Discord Bot is a modular Discord bot built with Python and `discord.py`. It provides server management, music playback, role panels, tickets, Join-to-Create temporary voice channels, messaging tools, document conversion, and other everyday server utilities.

Discord events and features are separated into independent modules, while the Core layer manages module lifecycle, settings, SQLite databases, logging, and error reporting. The Module Loader supports dependency validation and ordered loading, keeping features maintainable while leaving room for future expansion.

Most day-to-day features use Slash Commands and interactive panels. Owner tools provide maintenance controls for modules, settings reloads, command synchronization, Discord presence, error reporting, and safe shutdowns.

### Features

- Server utilities: welcome and leave messages, autoroles, server configuration, and basic information commands.
- Moderation: warnings, timeouts, moderation logs, and permission checks.
- Music: YouTube search and playback, playlists, queues, favorites, looping, volume control, and an interactive control panel.
- Community tools: self-role panels, tickets, and Join-to-Create temporary voice channels.
- Messaging and documents: regular messages, embeds, webhook sending, and common document conversion through `/markitdown`.
- Operations: module loading and reloading, Slash Command synchronization, settings validation, logging, error reporting, and an Owner control panel.

### Installation

Requirements:

- Python 3.11 or newer.
- A Discord Bot Token.
- FFmpeg when using music playback.
- Network access to Discord and YouTube.

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/oMiki0826o/discord-bot.git
cd discord-bot
python3.11 -m venv .venv
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

To reproduce the dependency versions verified for the release, use:

```bash
python -m pip install -r requirements-lock.txt
```

Copy the environment template:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Then edit `.env`:

```env
DISCORD_TOKEN=your_discord_bot_token
OWNER_ID=your_discord_user_id
```

`DISCORD_TOKEN` is used to log the bot in. `OWNER_ID` enables Owner management commands. Other non-secret feature settings are stored under `settings/`.

### Usage

After creating the bot in the Discord Developer Portal, enable the Privileged Gateway Intents required by the features you use. Invite the bot with the `bot` and `applications.commands` scopes, and grant only the permissions needed by the enabled features instead of relying on Administrator access.

Start the bot with:

```bash
python main.py
```

Useful first commands:

```text
/help
/ping
/botinfo
```

`/help` lists commands from the modules currently loaded by the bot. Music, tickets, roles, and voice features are operated through their Slash Commands and interactive panels.

Owner commands use the `$` prefix by default. Common entry points include:

```text
$help
$bot
$mod
$settings
$slash
$presence
$error
```

For a safe shutdown:

```text
$bot stop
```

Runtime SQLite databases and logs are stored under `data/`. For implementation details, see [Architecture](./docs/ARCHITECTURE.md), [Development Guide](./docs/DEVELOPMENT.md), and [Module Development](./docs/MODULE_DEVELOPMENT.md).

### License

This project is licensed under the MIT License, see [LICENSE](./LICENSE).
