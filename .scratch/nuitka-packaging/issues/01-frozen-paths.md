# 01: 打包後路徑解析

**What to build:** 新增 `app_paths.py`，讓 GUI 與日誌在原始碼執行與打包後都能找到正確位置；GUI 的 `targets.txt` 與報告預設改寫到 `%LOCALAPPDATA%\FireWallExcelFinder`。

**Blocked by:** 無

**Status:** ready-for-agent

- [x] `app_paths.py` 提供 `is_frozen()`、`executable_path()`、`application_directory()`、`user_data_directory()`、`ensure_user_data_directory()`、`resource_path()`。
- [x] 打包判斷使用 `__main__.__compiled__.original_argv0`，不依賴 `sys.frozen`。
- [x] `app_logging.py` 改用 `app_paths` 的 `APP_DIRECTORY` 與 `local_app_data_directory()`。
- [x] GUI 的預設目標檔、另存目標檔、報告輸出路徑改用應用程式資料目錄。
- [x] 資料目錄無法建立時退回目前工作目錄，並在狀態列說明。
- [x] CLI 的 `--dir`、`--target` 維持目前工作目錄語意。
- [x] `tests/test_app_paths.py` 與 GUI 預設路徑測試通過。
