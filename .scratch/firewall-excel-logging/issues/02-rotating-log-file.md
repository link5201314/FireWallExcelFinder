# 02: 輪替日誌檔

**What to build:** 每次啟動程式都會在 `%LOCALAPPDATA%\FireWallExcelFinder\logs\firewall_excel_finder.log` 附加寫入日誌；目錄不存在時自動建立。檔案使用 UTF-8 與固定格式（本地時間、毫秒、等級、logger 名稱），單檔達 5 MiB 時輪替，最多保留 3 個舊檔。`file` 等級與 `ui` 等級各自獨立，既有 warnings 與 errors 都會進入檔案。

**Blocked by:** 01（控制檔與有效日誌設定）

**Status:** ready-for-agent

- [ ] 日誌目錄與檔案不存在時自動建立；日誌以 append 模式寫入，不覆蓋既有內容。
- [ ] 日誌檔以 UTF-8 編碼，中文檔名、工作表名稱與錯誤訊息可正確閱讀。
- [ ] 每行格式為 `時間 等級 logger: 訊息`，時間為本地時間並含毫秒。
- [ ] 檔案 sink 套用控制檔的 `file` 等級；`ui` 等級的調整不影響檔案內容。
- [ ] 預設 `file=INFO` 時，日誌檔包含啟動與有效設定；`file=ERROR` 時只保留 ERROR 以上訊息。
- [ ] 既有掃描 warning 與 error 會出現在日誌檔，且不改變原本的 GUI／CLI 呈現。
- [ ] 單檔上限為 5 MiB（5 × 1024 × 1024 bytes）；達到上限後輪替，目錄中最多保留現行檔加 3 個舊檔。
- [ ] 測試先在暫存目錄預置一個超過 5 MiB 的日誌檔，執行一次 CLI 後斷言產生 `.log.1`，且新檔重新開始累積。
- [ ] 測試涵蓋 `file=INFO` 與 `file=ERROR` 的內容差異、UTF-8 中文、時間與 logger 格式。
- [ ] `uv run pytest` 全綠，`uv run ruff check` 無新錯誤。

**Definition of Done:** 上述驗收項目全部通過；日誌檔的建立、內容與輪替都能只靠執行既有入口觀察到。
