# 07: 使用說明

**What to build:** README 讓使用者與維護者能自行完成日誌設定與問題回報：說明控制檔位置與 schema、`ui` 與 `file` 的差異與預設值、日誌檔位置、UTF-8 與輪替規則、失敗降級行為，以及同時開啟多個實例的限制。

**Blocked by:** 03（掃描生命週期與隱私邊界）、04（GUI 日誌分頁）、05（日誌失敗降級）、06（未捕捉例外記錄）

**Status:** ready-for-agent

- [ ] README 說明 `%LOCALAPPDATA%\FireWallExcelFinder\logging.ini` 的位置、`[levels]` schema、可接受等級值與預設值。
- [ ] README 說明 `ui` 對應 GUI 日誌分頁與 CLI stderr，`file` 對應日誌檔，兩者互相獨立。
- [ ] README 說明日誌檔位置、UTF-8、append、5 MiB 上限與保留 3 個舊檔。
- [ ] README 說明設定或日誌檔建立失敗時的降級行為，以及如何確認目前有效設定。
- [ ] README 說明同時開啟多個 CLI／GUI 實例時，共用日誌檔的輪替限制。
- [ ] README 說明日誌不會記錄儲存格完整文字與目標規則原始行。
- [ ] 文件內容與實際行為一致，不出現已過期的檔案路徑清單或實作細節。
- [ ] `CONTEXT.md` 不變，日誌相關詞彙不被寫入領域詞彙表。
- [ ] 文件中的指令可直接執行，且與現有 `uv` 工作流程一致。

**Definition of Done:** 上述驗收項目全部通過；只讀 README 就能完成設定、找到日誌並理解限制。
