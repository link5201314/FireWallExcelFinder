# 06: 未捕捉例外記錄

**What to build:** 主執行緒與背景執行緒發生未捕捉例外時，程式把 traceback 以 CRITICAL 寫入日誌檔與當下可用的 UI sink。GUI 不新增崩潰對話框，CLI 的退出碼語意維持不變。

**Blocked by:** 02（輪替日誌檔）

**Status:** ready-for-agent

- [ ] 安裝 `sys.excepthook`，未捕捉例外以 CRITICAL 記錄完整 traceback。
- [ ] 安裝 `threading.excepthook`，背景執行緒的未捕捉例外同樣以 CRITICAL 記錄 traceback。
- [ ] 例外記錄會同時送往檔案 sink 與 UI sink（GUI 日誌分頁或 CLI stderr），並遵守各自的等級設定。
- [ ] 不新增崩潰對話框，也不改變既有 Qt 事件迴圈行為。
- [ ] CLI 未捕捉例外後的退出碼與原本 Python 行為一致，不因日誌 hook 而改變。
- [ ] 日誌初始化尚未完成或檔案 sink 停用時，hook 仍安全，不因記錄失敗而二次崩潰。
- [ ] 測試以獨立程序執行最小腳本觸發未捕捉例外，斷言日誌檔含 CRITICAL 與 traceback。
- [ ] 測試涵蓋背景執行緒丟出的未捕捉例外。
- [ ] `uv run pytest` 全綠，`uv run ruff check` 無新錯誤。

**Definition of Done:** 上述驗收項目全部通過；最需要日誌的崩潰時刻，日誌檔仍有完整現場。
