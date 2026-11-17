# 日誌輸出控制與輪替

**Status:** ready-for-agent

## Problem Statement

目前 GUI 上看到的訊息只是狀態列文字與掃描結果的 warnings，並不是真正的日誌管線；程式也沒有任何可長期保存的日誌檔。當掃描結果不如預期、活頁簿讀取失敗或程式在背景執行緒出錯時，使用者與維護者只能在當下畫面上找線索，關掉程式後就什麼都不剩，也無法請使用者把現場資訊帶回來。

另一方面，GUI 使用者不想被大量訊息淹沒，維護者卻需要較詳細的檔案。若只有一個全域等級，兩邊的需求會互相拉扯：調高到可診斷的程度會讓畫面吵雜，調低則讓日誌檔失去價值。

## Solution

為 GUI 與 CLI 建立共用的日誌管線，將輸出分成兩個獨立的 sink：

- **UI**：GUI 新增「日誌」分頁；CLI 的 console（stderr）視為同一個 UI sink。
- **檔案**：寫入 `%LOCALAPPDATA%\FireWallExcelFinder\logs\firewall_excel_finder.log`。

兩邊的等級由 `%LOCALAPPDATA%\FireWallExcelFinder\logging.ini` 分別控制，首次啟動自動建立並附上繁中註解。日誌檔以 UTF-8 附加寫入，單檔上限 5 MiB，保留 3 個舊檔。所有日誌設定錯誤都只會降級，不會阻止程式啟動或掃描。

GUI 的「警告」分頁維持原職責，只顯示掃描結果的 warnings，不受 UI 日誌等級影響；狀態列與進度顯示也不屬於日誌等級控制範圍。

## User Stories

1. As a GUI 使用者, I want 在視窗中看到日誌訊息, so that 不必開 console 或翻檔案就能知道程式剛剛做了什麼。
2. As a GUI 使用者, I want 日誌與掃描警告分成兩個分頁, so that 我能分清楚「程式診斷」與「這次掃描的資料問題」。
3. As a GUI 使用者, I want 用控制檔調整 UI 等級, so that 平常畫面保持安靜、需要時再打開細節。
4. As a GUI 使用者, I want UI 等級預設為 WARNING, so that 第一次開啟程式不會被大量訊息淹沒。
5. As a GUI 使用者, I want 啟動時看到一行有效日誌設定, so that 我能確認控制檔到底有沒有被讀到。
6. As a GUI 使用者, I want 一鍵清除日誌面板, so that 我能把畫面留給接下來的操作。
7. As a GUI 使用者, I want 從介面開啟日誌資料夾, so that 我能直接把日誌檔交給維護者。
8. As a GUI 使用者, I want 日誌面板自動捲到最新一筆, so that 我不必手動追蹤目前進度。
9. As a GUI 使用者, I want 日誌面板只保留最近 1,000 行, so that 長時間執行也不會耗盡記憶體。
10. As a GUI 使用者, I want 掃描警告分頁不受 UI 等級過濾, so that 即使 UI 設成 ERROR，我仍看得到損毀活頁簿的警告。
11. As a GUI 使用者, I want 狀態列與進度條維持原本行為, so that 日誌設定不會改變我熟悉的操作回饋。
12. As a GUI 使用者, I want 日誌等級不影響掃描結果與報告, so that 調高紀錄詳細度不會改變命中內容。
13. As a GUI 使用者, I want 日誌檔無法建立時仍能完成掃描, so that 權限或磁碟問題不會擋住主要工作。
14. As a GUI 使用者, I want UI 等級設為 ERROR 時仍看到真正的錯誤, so that 我能在最小雜訊下抓到失敗原因。
15. As a GUI 使用者, I want UI 等級設為 DEBUG 時看到每個檔案的處理細節, so that 我能定位是哪個活頁簿拖慢或失敗。
16. As a GUI 使用者, I want 日誌檔放在 `%LOCALAPPDATA%`, so that 不需要系統管理權限也能寫入。
17. As a GUI 使用者, I want 每次啟動附加到同一個日誌檔, so that 跨次執行的線索不會被覆蓋。
18. As a GUI 使用者, I want 檔案等級與 UI 等級獨立, so that 我能「畫面安靜、檔案詳細」。
19. As a GUI 使用者, I want 檔案等級預設為 INFO, so that 預設就有基本的執行線索。
20. As a GUI 使用者, I want 單一日誌檔上限 5 MiB, so that 日誌不會無限制成長。
21. As a GUI 使用者, I want 保留 3 個舊日誌檔, so that 最近的歷史仍可追查，同時磁碟用量有上限。
22. As a GUI 使用者, I want 日誌以 UTF-8 儲存, so that 中文檔名、工作表名稱與錯誤訊息都能正確閱讀。
23. As a GUI 使用者, I want 每筆日誌都有含毫秒的時間戳記, so that 我能排出同一秒內事件的順序。
24. As a GUI 使用者, I want 每筆日誌標示來源 logger, so that 我能分辨訊息來自 GUI 還是掃描核心。
25. As a 維護者, I want 日誌記錄啟動、設定載入、掃描參數、完成統計與報告寫入, so that 我能從單一檔案重建一次執行的脈絡。
26. As a 維護者, I want 每個檔案的處理在 DEBUG 等級留下紀錄, so that 我能找出個別活頁簿的問題。
27. As a 維護者, I want 日誌不記錄儲存格完整文字與目標規則原始行, so that 敏感資料不會長期落盤。
28. As a 維護者, I want 未捕捉例外以 CRITICAL 記錄 traceback, so that 程式崩潰時仍有現場可查。
29. As a 維護者, I want 背景執行緒的未捕捉例外也被記錄, so that 掃描執行緒的失敗不會無聲消失。
30. As a 使用者, I want 控制檔第一次啟動自動建立, so that 我不必先讀文件才知道格式。
31. As a 使用者, I want 控制檔附上繁中註解與預設值, so that 我能直接編輯而不猜測。
32. As a 使用者, I want 等級名稱不分大小寫, so that 手動輸入不會因為大小寫而失效。
33. As a 使用者, I want 非法等級值自動退回預設並留下警告, so that 打錯字不會讓程式起不來。
34. As a 使用者, I want 控制檔格式錯誤時仍能啟動, so that 一個設定失誤不會擋住掃描。
35. As a 使用者, I want 未知的鍵或區段被忽略, so that 我多寫的設定不會造成錯誤。
36. As a 使用者, I want 控制檔在啟動時讀取一次, so that 行為可預期，不會執行到一半突然改變。
37. As a 使用者, I want 控制檔與日誌檔的位置固定且可預期, so that 我能備份、清理或回報問題。
38. As a CLI 使用者, I want CLI 與 GUI 共用同一套日誌設定, so that 兩個入口的行為不會分叉。
39. As a CLI 使用者, I want CLI 的 console 等級由 `ui` 控制, so that 同一個控制檔就能調整終端機輸出。
40. As a CLI 使用者, I want 預設 console 行為維持 WARNING, so that 既有自動化流程的輸出不變。
41. As a CLI 使用者, I want 既有參數與退出碼維持不變, so that 自動化腳本不需要修改。
42. As a CLI 使用者, I want 同時開啟 CLI 與 GUI 時仍可運作, so that 我不必擔心兩個實例互相鎖死。
43. As a 測試維護者, I want 測試完全不接觸真實 `%LOCALAPPDATA%`, so that 跑測試不會污染我的日誌與設定。
44. As a 測試維護者, I want 日誌初始化可重複執行而不重複輸出, so that 連續建立多個視窗的測試不會得到重複行。
45. As a 測試維護者, I want 視窗關閉後 UI handler 不再持有 widget, so that 測試不會因為已刪除的 Qt 物件而不穩定。

## Implementation Decisions

- 新增一個內部日誌模組，負責：解析控制檔、建立兩個 sink、提供 Qt UI handler、安裝未捕捉例外鉤子。GUI 與 CLI 都呼叫同一個初始化介面，不各自複製設定邏輯。
- GUI 在建立主視窗時完成日誌初始化，並把該視窗的 UI handler 交給共用初始化介面；CLI 在進入 `main` 流程時初始化，不傳 UI handler，改由 stderr 作為 UI sink。GUI 的初始化可重複執行，讓測試能只透過建立視窗走真實設定路徑。
- 控制檔固定為 `%LOCALAPPDATA%\FireWallExcelFinder\logging.ini`。INI schema 只有一個 `[levels]` 區段，鍵為 `ui` 與 `file`；值為 `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`，比較時不分大小寫。預設值 `ui=WARNING`、`file=INFO`。未知區段與鍵忽略。
- 控制檔不存在時自動建立，內容為 UTF-8 並附繁中註解。無法建立、無法讀取、格式錯誤或等級非法時，一律使用預設值，並在可用的 sink 留下一筆警告；初始化流程不得拋出例外給呼叫端。
- 日誌檔固定為 `%LOCALAPPDATA%\FireWallExcelFinder\logs\firewall_excel_finder.log`，UTF-8、append 模式。使用標準函式庫的輪替檔案 handler，單檔上限 5 MiB（5 × 1024 × 1024 bytes），`backupCount=3`，即目錄中最多 4 個檔：現行檔加上 3 個舊檔。
- `%LOCALAPPDATA%` 未定義時退回 `Path.home() / "AppData" / "Local"`；若日誌目錄或檔案仍無法建立，停用檔案 sink，程式其餘功能照常運作，並在 UI sink 留下一筆 ERROR。
- 日誌行格式固定為 `%(asctime)s %(levelname)s %(name)s: %(message)s`，使用本地時間並包含毫秒；此格式不開放控制檔調整。
- UI sink 與檔案 sink 各自套用對應等級。GUI 的「日誌」分頁與 CLI 的 stderr 都屬於 UI sink；CLI 的 stdout 報告輸出不受日誌設定影響。
- GUI 主視窗把底部警告區改為兩個分頁：「日誌」與「警告」。「日誌」分頁唯讀、自動捲到底、保留最近 1,000 行，並提供「清除」與「開啟日誌資料夾」操作；預設選中「日誌」分頁。
- 「警告」分頁維持現有來源與內容，只顯示掃描結果的 warnings，不受 `ui` 等級過濾。狀態列、進度條與摘要文字也不受日誌等級影響。
- UI handler 是 logging handler，透過 Qt signal 把格式化後的訊息送回主執行緒，再由主執行緒更新面板；不得從背景執行緒直接操作 widget。視窗關閉時解除並移除自家 handler，避免持有已刪除的 Qt 物件。
- 日誌初始化必須可重複執行：每次初始化先移除本程式先前加入的 handler，再加入目前的 handler，確保同一個程序內多次建立視窗不會產生重複行。
- 生命週期日誌點：程式啟動與有效設定（含控制檔路徑與日誌檔路徑）、掃描開始參數（目錄、遞迴、工作表關鍵字、選取規則數）、每個檔案的處理結果（DEBUG，僅檔名與該檔命中數）、掃描完成統計、報告寫入成功或失敗。既有 warning/error 呼叫保留並接入同一管線。
- 日誌內容不得包含儲存格完整文字、目標規則原始行或命中 Token 的上下文。允許記錄檔案路徑、檔名、工作表名稱、座標、掃描參數、統計數字與例外訊息。
- 安裝 `sys.excepthook` 與 `threading.excepthook`，把未捕捉例外的 traceback 以 CRITICAL 寫入可用 sink。不新增崩潰對話框，也不改變既有退出碼語意。
- CLI 的 console sink 使用 stderr，以維持現行 `basicConfig` 的流向；預設 `ui=WARNING` 讓既有 CLI 外部行為不變。
- 控制檔只在啟動時讀取一次；執行中修改需重新啟動程式才生效，不提供熱重載。
- 同時開啟多個 CLI/GUI 實例時，共用同一個日誌檔；標準輪替 handler 不是多程序安全的，可能遺失少量訊息或產生非預期輪替。此限制寫入文件，不在本次解決。
- 不新增第三方依賴；只使用 Python 標準函式庫的 logging 與 configparser。既有 `docs/adr/0001-logging-control-file-and-rotation.md` 是本次的架構決策來源。
- 更新 README，說明控制檔位置、等級語意、日誌檔位置、輪替規則、失敗降級行為與多程序限制。`CONTEXT.md` 不變，因為日誌屬基礎設施而非領域詞彙。

## Testing Decisions

- 好測試只驗證外部可觀察行為：給定 `%LOCALAPPDATA%` 與控制檔，執行既有入口後觀察日誌檔、stderr、退出碼與 GUI widget 內容；不直接呼叫私有 handler、不檢查 logging 物件內部狀態。
- 主要接縫沿用既有的兩個：CLI 以現有 subprocess helper 執行，GUI 以既有 `MainWindow` 工作流程操作。兩者都只透過把 `%LOCALAPPDATA%` 導向 `tmp_path` 來控制設定，不新增測試專用 API。
- 新增 autouse fixture 將 `%LOCALAPPDATA%` 導向每個測試的暫存目錄，確保任何測試都不會寫入真實使用者目錄；既有測試不需改寫掃描邏輯。
- 輪替測試不調整 handler 參數：先在暫存日誌目錄預置一個超過 5 MiB 的日誌檔，再執行一次 CLI，斷言產生 `.log.1`，且新檔重新開始累積。
- CLI 測試沿用 `run_cli` 先例：建立暫存 Excel 與目標檔、執行 CLI、斷言 stdout／stderr／退出碼與日誌檔內容。
- GUI 測試沿用 `make_window`、`get_widget`、`QSignalSpy`、Qt offscreen 與 `tmp_path` 先例；以 widget 文字與按鈕行為驗證，不使用固定睡眠。
- 需涵蓋的日誌行為：首次啟動自動建立控制檔；預設等級；`ui` 與 `file` 分別過濾；非法等級與損壞 INI 的降級；未知鍵忽略；日誌目錄無法建立時的降級；輪替與保留份數；UTF-8 中文內容；時間戳與 logger 名稱格式。
- 需涵蓋的 GUI 行為：「日誌」分頁顯示符合 `ui` 等級的訊息；`ui=ERROR` 時 warning 不出現在日誌分頁但仍在「警告」分頁；「清除」清空面板；「開啟日誌資料夾」指向正確目錄（以替身攔截外部開啟動作，不真的啟動檔案總管）；面板保留 1,000 行上限。
- 需涵蓋的隱私邊界：掃描含敏感文字的儲存格後，斷言該文字與目標規則原始行不出現在日誌檔。
- 未捕捉例外測試以獨立程序執行最小腳本，讓例外真的觸發 hook，再斷言日誌檔含 CRITICAL 與 traceback；這是程序層級的外部行為測試，不是單元測試。
- 既有測試先例是隔離目錄、程式化 Excel fixture、CLI subprocess 與 GUI 工作流程；新測試延續相同原則，只依賴暫存資料，不發出網路請求，也不使用真實使用者活頁簿。

## Out of Scope

- 執行中熱重載控制檔，或在 GUI 內即時切換等級。
- 針對個別模組、logger 或訊息內容的等級與過濾規則。
- 由控制檔調整日誌路徑、檔名、輪替大小、保留份數或訊息格式。
- CLI 新增 `--log-level`、`--log-file` 等日誌相關參數。
- 日誌檢視器、搜尋、匯出、手動觸發輪替或日誌封存。
- 遠端日誌、syslog、JSON 結構化日誌或日誌聚合服務。
- 超出「不記錄儲存格文字與目標規則原始行」之外的通用敏感資料掃描或遮罩。
- 改變「警告」分頁、狀態列、進度條或報告輸出的既有語意。
- 跨程式執行保存 GUI 設定或日誌面板狀態。
- 修改 `CONTEXT.md` 或新增領域詞彙。

## Further Notes

- 本規格依 `docs/adr/0001-logging-control-file-and-rotation.md` 的已定案決策撰寫；ADR 記錄了控制檔位置、雙 sink 等級、輪替與多程序限制的取捨。
- 現況與需求描述有一個落差：目前 GUI 上的訊息來自狀態列與 `warnings`，不是 logging 管線；本規格會建立真正的日誌管線，並保留既有狀態列與 warnings 的行為。
- 「UI」在本規格中同時指 GUI 的「日誌」分頁與 CLI 的 stderr；「檔案」指輪替日誌檔。
- 「保留 3 個舊檔」解讀為現行檔加 3 個輪替檔，總共最多 4 個檔案。
- 日誌是輔助功能：任何日誌設定或檔案系統問題都不得阻止掃描、報告輸出或程式啟動。
