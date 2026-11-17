# 打包為 Windows 可攜版（Nuitka）

**Status:** ready-for-agent

## Problem Statement

目前專案只能以原始碼搭配 uv 執行，目標電腦必須先安裝 Python 與相依套件。對只負責使用掃描工具的同仁而言，這是一個不必要的門檻；版本漂移也會讓「我這邊跑得起來」變成常態。

## Solution

以 Nuitka 產生兩個 standalone 目錄：GUI 版與 CLI 版。目標電腦不需安裝 Python，整包複製即可執行。建置流程固定使用 `--lto=yes`，現階段不做程式簽署，簽署留待之後以 `signtool` 處理。

打包後的路徑語意必須明確：GUI 的 `targets.txt` 與報告預設寫入 `%LOCALAPPDATA%\FireWallExcelFinder`，與日誌相同；CLI 維持以目前工作目錄解析相對路徑。

## Implementation Decisions

- 新增 `app_paths.py` 集中路徑邏輯：`is_frozen()`、`application_directory()`、`user_data_directory()`、`resource_path()`。以 Nuitka 注入的 `__main__.__compiled__.original_argv0` 判斷是否打包，避免依賴 `sys.frozen`（Nuitka 未設定）。
- GUI 的預設目標檔與報告路徑改用 `ensure_user_data_directory()`；無法建立目錄時退回目前工作目錄並在狀態列提示。掃描目錄與瀏覽對話框起始位置維持目前目錄。
- CLI 的 `--dir` 與 `--target` 預設值不變，仍相對目前工作目錄；README 說明捷徑需傳絕對路徑或設定「開始位置」。
- `app_logging.py` 改從 `app_paths` 取得 `APP_DIRECTORY` 與 `local_app_data_directory()`，保留同名匯出供既有測試使用。
- 圖示為 `assets/app.ico`（16～256 多尺寸，由 `assets/app-icon.png` 轉出）；Nuitka 以 `--windows-icon-from-ico` 嵌入，並以 `--include-data-files` 供視窗圖示使用。缺少圖示時靜默略過。
- 建置環境為 uv 管理的 Python 3.13 + MinGW64 GCC 15.2.0，需同時加上 `--mingw64` 與 `--experimental=force-mingw64`；若改裝 Visual Studio 2022 Build Tools，可換成 `--msvc=latest`。
- 所有建置指令必須包含 `--update-check=never`：uv 管理的 Python 3.13 執行 Nuitka 更新檢查時會以 `OPENSSL_Uplink ... no OPENSSL_Applink` 中止。
- GUI 使用 `--enable-plugin=pyside6` 與 `--windows-console-mode=disable`；CLI 使用 `--windows-console-mode=force`。兩者皆 `--mode=standalone` 與 `--lto=yes`。
- 產物輸出到 `build\nuitka\`，沿用既有 `.gitignore` 的 `build/`；另補 `*.build/`、`*.dist/`、`*.onefile-build/`。
- 本次不處理簽署、安裝程式、onefile 模式與 ARM64 建置。

## Testing Decisions

- `tests/test_app_paths.py` 驗證原始碼模式與打包模式的目錄解析、資源路徑，以及資料目錄無法建立時的錯誤。
- GUI 測試驗證預設目標檔位於 `%LOCALAPPDATA%\FireWallExcelFinder`，且資料目錄不可用時退回目前目錄。
- 建置後以不同工作目錄啟動 GUI 與 CLI，掃描暫存活頁簿並比對報告；確認日誌檔、`targets.txt` 與報告位置符合預期。
- 既有 `pytest` 與 `ruff` 必須全綠。

## Out of Scope

- 程式簽署、SmartScreen 信譽建立。
- 安裝程式、開始功能表捷徑、自動更新。
- onefile 模式與跨平台（Linux／macOS）建置。
- 變更 CLI 既有的相對路徑語意或退出碼。
