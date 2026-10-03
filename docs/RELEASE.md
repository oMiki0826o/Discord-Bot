# 發布指南

正式發布時，請從原始碼建立乾淨的 ZIP，不要直接壓縮日常工作的專案資料夾。

## 建立 ZIP

先完成測試：

```bash
python -m pytest -q
python -m compileall -q bot tools tests main.py
git diff --check
```

再執行：

```bash
python tools/build_release.py
```

預設輸出：

```text
dist/Discord-Bot-v0.1.0.zip
```

壓縮包內會有單一根目錄 `Discord-Bot-v0.1.0/`，方便解壓後直接使用。

## 一定不應進入發布包的內容

- `.env`、`.env.local`。
- `.git/` 與其他 VCS metadata。
- `.venv/`、`venv/`。
- `data/`、SQLite、Log、AI 使用者記憶與 Prompt override。
- `settings/*.json` 部署端設定。
- `__pycache__/`、`.pytest_cache/`、`.ruff_cache/`、`.mypy_cache/`。
- `.DS_Store`、`__MACOSX/` 等作業系統附加檔。
- `dist/` 舊發布物。
- `tools/` 維護端封裝與匯入工具。
- `.superpowers/`、`docs/superpowers/` 等內部工作規格與代理執行紀錄。

`settings/README.md` 與 `.env.example` 會保留，讓使用者知道設定位置與必要環境變數。

## 發布前人工確認

1. `.env.example` 不包含真實 Token / API Key。
2. README 的啟動入口為 `python main.py`。
3. `requirements.txt` 與 `requirements-lock.txt` 符合本次驗證版本。
4. 必要 Module 可以正常載入，且 `modules.required` 沒有被停用。
5. Slash Command、Owner Prefix Command、Module reload 與安全關閉至少做一次實機測試。
6. 若更新 AI model pool，確認模型 ID 與帳號實際可用額度，而不是只看名稱存在。
