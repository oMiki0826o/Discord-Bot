# Settings

這個目錄保存 Bot 執行期間的非機密 JSON 設定。

第一次啟動時，Core 與各功能模組會依自己的 `DEFAULT_SETTINGS` 自動建立需要的 `settings/*.json`；既有設定只會補上缺少的預設欄位，並依 schema 驗證型別與範圍。

`settings/*.json` 屬於部署端設定，因此預設不納入版本控制與正式發布包。Token、API Key 等機密資料不可放在這裡，請使用專案根目錄的 `.env`。
