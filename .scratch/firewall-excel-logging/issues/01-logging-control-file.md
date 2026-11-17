# 01: 控制檔與有效日誌設定

**What to build:** 使用者第一次啟動程式時，系統自動在 `%LOCALAPPDATA%\FireWallExcelFinder\logging.ini` 建立附繁中註解的控制檔；之後每次啟動都讀取 `[levels]` 下的 `ui` 與 `file` 等級，並在 stderr 留下一行「有效日誌設定」，讓使用者能確認設定是否生效。設定缺漏、格式錯誤或等級非法時一律退回預設值並留下警告，程式照常啟動。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 控制檔不存在時自動建立，內容包含 `[levels]` 區段、`ui = WARNING`、`file = INFO` 與繁中註解說明可接受的等級值。
- [ ] 等級值 `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL` 不分大小寫都能正確解析。
- [ ] 缺少 `[levels]`、缺少鍵、等級值非法或 INI 格式損壞時，使用對應預設值，並在 stderr 留下一筆警告；初始化流程不拋出例外。
- [ ] 未知的區段或鍵被忽略，不影響啟動。
- [ ] 啟動時以 INFO 在 stderr 輸出一行有效設定，至少包含 `ui` 等級、`file` 等級與控制檔路徑。
- [ ] `ui` 等級套用到 stderr；預設 `WARNING` 時，既有 CLI 的 stdout 報告、stderr 警告與退出碼維持不變。
- [ ] 測試以 autouse fixture 將 `%LOCALAPPDATA%` 導向每個測試的暫存目錄，任何測試都不會寫入真實使用者目錄。
- [ ] 新增測試涵蓋：自動建立、預設值、大小寫不敏感、非法值降級、損壞 INI 降級、未知鍵忽略、CLI 既有行為不變。
- [ ] `uv run pytest` 全綠，`uv run ruff check` 無新錯誤。

**Definition of Done:** 上述驗收項目全部通過，且變更不影響既有掃描與報告行為。
