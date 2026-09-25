# 開發指南

## 建立環境

```bash
git clone https://github.com/oMiki0826o/Discord-Bot.git
cd Discord-Bot
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Windows PowerShell：

```powershell
.venv\Scripts\Activate.ps1
```

建立 `.env` 後即可用：

```bash
python main.py
```

## 修改前先找對位置

- 共用能力：`bot/core/`
- 功能邏輯：`bot/mod/<module>/`
- 公開設定：`settings/`
- 離線測試：`tests/`

單一功能需要的設定、資料庫與 UI 優先留在該模組內；只有確定會跨模組重用的能力才放進 Core。

## Python 檔案格式

一般 `.py` 檔案在頂部保留檔名、修改摘要與用途說明。完全空白的 `__init__.py` 可省略檔頭。

區段註解統一使用：

```python
# ── 區段名稱 ──────────────────────
```

修改既有檔案時，順手整理過時註解，讓註解描述目前程式，而不是保留已經失效的歷史狀態。

## Settings

設定分成兩類：

- `.env`：Token、Secret 與部署層級資訊。
- `settings/*.json`：一般功能設定。

新增設定時，同步更新模組預設值與 Schema。舊設定檔缺少欄位時會自動補齊，但型別錯誤或超出限制應直接在載入階段被攔下。

## 模組生命週期

修改模組時特別注意：

- `setup()` 中途失敗後是否有完整回滾。
- `teardown()` 是否能安全重複執行。
- reload 後是否留下重複 Cog、Command、View、Task 或 Handler。
- 有跨模組前置需求時是否宣告 `MODULE_DEPENDENCIES`。
- 關閉前是否釋放播放器、連線與背景工作。

## 例外處理

可預期的 Discord、I/O、逾時與轉換錯誤應盡量捕捉具體型別。最外層生命週期、第三方函式庫或回滾邊界可以保留 `except Exception`，但必須留下 log、完成回滾或重新拋出；不要用空白 `pass` 把錯誤吃掉。

對使用者顯示的錯誤訊息應說明「哪裡失敗」與「可以怎麼處理」，不要直接把大型 traceback 或內部例外堆疊丟到 Discord。

## 發布前測試

先執行離線測試：

```bash
python -m pytest -q
python -m compileall -q bot main.py tests
```

再用乾淨的 Runtime Data 啟動一次 Bot，至少實際測：

- `/help`、`/ping`、`/botinfo`
- 模組載入、卸載與 reload
- Slash Command 同步
- 音樂播放、暫停、跳過、停止、佇列與收藏
- Voice Join-to-Create
- Ticket 建立與關閉
- 身分組面板
- Moderation
- 安全關閉與日誌輸出

涉及 Discord 權限、Voice、FFmpeg、yt-dlp 或網路服務的功能，離線測試無法取代實際 Bot 驗收。

## 音樂功能

開發音樂模組前確認：

```bash
ffmpeg -version
python -m yt_dlp --version
```

若出現 YouTube `403 Forbidden`、簽名解析錯誤或串流網址過期，先更新 `yt-dlp` 並重新重現，再判斷是否為程式本身的問題。

## 發布包整理

發布前確認沒有混入：

```text
.env
data/
*.db
*.log
__pycache__/
*.pyc
.venv/
.pytest_cache/
```

`requirements.txt` 保存可接受的版本範圍；`requirements-lock.txt` 保存發布時選定的直接依賴版本。更新依賴後應重新跑測試再同步兩份檔案。
