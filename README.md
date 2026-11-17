# FireWallExcelFinder

## 離線掃描防火牆 Excel

掃描器以 IPv4 區間交集比對目標規則與 Excel 儲存格中的位址，支援單一 IPv4、完整範圍、同一 `/24` 的末碼簡寫範圍及 CIDR。執行時不連線至外部服務，並以唯讀方式逐格掃描 `.xlsx` 活頁簿。

```powershell
# 使用目前目錄與預設 targets.txt
uv run python audit_firewall_ips.py

# 指定 Excel 目錄、目標檔、遞迴掃描、工作表篩選及 CSV 報告
uv run python audit_firewall_ips.py --dir .\excel --target .\targets.txt --recursive --sheets 正式區 測試區 --output .\report.csv

# 啟動 PySide6 視窗介面
uv run python firewall_gui.py
```

## PySide6 視窗介面

安裝專案依賴後即可啟動 GUI：

```powershell
uv sync
uv run python firewall_gui.py
```

視窗可選擇 Excel 掃描目錄、載入／編輯／儲存目標規則、設定工作表關鍵字、遞迴掃描、完整儲存格文字與 TXT/CSV 報告。目標規則可逐條勾選，勾選狀態只在目前工作階段有效。若目標內容尚未儲存，開始掃描前必須先儲存；沒有已載入的檔案路徑時會要求另存新檔，以確保報告中的來源行號對應實際目標檔。

GUI 匯出 CSV 時會另外產生同名的 `.summary.txt` 摘要檔，記錄掃描統計、部分失敗狀態與活頁簿警告；CSV 本身仍維持既有欄位格式。

掃描在背景執行，可取消；完成後可在「檔案位置」與「目標規則」兩種可展開／摺疊的樹狀檢視間切換，而不需重新掃描。檔案位置模式依 `file → sheet → coordinate` 合併節點；目標規則模式依 `(target_line, target)` 合併，再按檔案位置分組。

既有 CLI 仍可照原方式使用；GUI 與 CLI 共用相同的掃描與位址比對邏輯。

目標檔每行一條規則，空白行及以 `#` 開頭的整行會忽略。格式錯誤的目標行會警告後略過。未指定報告檔時，命中明細與摘要輸出至 Console；指定 `.txt` 或 `.csv` 報告時，摘要仍輸出至 Console。加上 `--verbose` 可顯示命中儲存格的完整文字；預設只掃描指定目錄第一層，加上 `--recursive` 才會掃描子目錄。

CSV 報告使用帶 UTF-8 BOM 的編碼，方便在 Windows 上直接以 Excel 開啟並正確顯示中文字元。

## 日誌

GUI 與 CLI 共用同一套日誌設定，輸出分成兩個獨立的 sink：

- **UI**：GUI 視窗底部的「日誌」分頁，以及 CLI 的 stderr。
- **檔案**：`%LOCALAPPDATA%\FireWallExcelFinder\logs\firewall_excel_finder.log`。

設定檔位於 `%LOCALAPPDATA%\FireWallExcelFinder\logging.ini`，第一次啟動時自動建立並附上繁中註解。可用的等級為 `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`（不分大小寫），預設值如下：

```ini
[levels]
ui = WARNING
file = INFO
```

`ui` 控制 GUI 日誌分頁與 CLI stderr，`file` 控制日誌檔；兩者互相獨立，可以做到「畫面安靜、檔案詳細」。修改後需重新啟動程式才會生效。GUI 底部的「警告」分頁只顯示該次掃描的資料問題，不受 `ui` 等級影響；狀態列與進度條也不受影響。

日誌檔以 UTF-8 附加寫入，每筆包含本地時間（毫秒）、等級與來源 logger，單檔上限 5 MiB，保留 3 個舊檔（現行檔加上 `.1`～`.3`）。GUI 的日誌分頁保留最近 1,000 行，並提供「清除」與「開啟日誌資料夾」。

日誌不會記錄儲存格完整文字、目標規則原始行或命中 Token 的上下文。設定檔損壞、等級值非法、日誌目錄無法建立或 `%LOCALAPPDATA%` 無法使用時，程式會退回預設等級或停用檔案輸出，並在可用的輸出留下警告，不會阻止啟動、掃描或報告輸出。未捕捉例外（含背景執行緒）會以 `CRITICAL` 記錄 traceback。

同時開啟多個 CLI／GUI 實例時會共用同一個日誌檔；標準輪替機制不具多程序安全性，可能遺失少量訊息或產生非預期輪替。

目標規則範例：

```text
# 單一 IPv4、CIDR、完整範圍、同一 /24 末碼簡寫
192.168.0.123
192.168.0.0/24
10.0.34.10-10.0.34.50
10.0.34.204-229
```

### CLI 參數

| 參數 | 用途 |
| --- | --- |
| `-d`, `--dir` | Excel 目錄，預設目前目錄 |
| `-t`, `--target` | 目標規則檔，預設 `targets.txt` |
| `-o`, `--output` | `.txt` 或 `.csv` 報告輸出 |
| `-s`, `--sheets` | 一個或多個工作表名稱關鍵字，不分大小寫、部分比對 |
| `-v`, `--verbose` | 顯示完整儲存格文字 |
| `-r`, `--recursive` | 啟用子目錄遞迴掃描；預設關閉 |

符號連結與以 `~$` 開頭的 Excel 暫存鎖定檔會略過。零命中仍回傳成功；輸入錯誤回傳結束狀態 `2`，部分活頁簿讀取失敗回傳 `1`。

## 環境管理

本專案使用 [uv](https://docs.astral.sh/uv/) 管理 Python 版本需求、相依套件與虛擬環境。

### 初始化

安裝 uv 後，在專案目錄執行：

```powershell
uv sync
```

`uv sync` 會依照 `pyproject.toml` 與 `uv.lock` 建立 `.venv` 並同步套件。請將 `uv.lock` 納入版本控制，以確保團隊使用一致的依賴版本。

### 管理套件

```powershell
# 新增執行時套件
uv add 套件名稱

# 新增開發用套件
uv add --dev 套件名稱

# 移除套件
uv remove 套件名稱
```

uv 會同步更新 `pyproject.toml` 與 `uv.lock`。執行 Python 程式或工具時可使用 `uv run`，例如 `uv run python <程式檔>`。

### 測試

```powershell
uv run pytest
```

`pytest` 僅列為開發依賴；執行期依賴為 `openpyxl` 與 `PySide6`。GUI 測試會使用 Qt offscreen 平台，不需要顯示器。

## 打包為 Windows 可攜版（Nuitka）

以 Nuitka 產生 standalone 目錄，目標電腦不需要安裝 Python 或 uv，整包複製即可執行。

### 前置需求

- Windows 10／11 x64。目前只建置 x64，ARM64 需另外處理。
- 第一次建置需要網路：Nuitka 會下載 MinGW64 與 ccache 到使用者快取。
- 約 2 GB 磁碟空間；`--lto=yes` 會明顯拉長連結時間並需要較多記憶體。

Python 3.13 以上不能直接使用 Nuitka 內建的 MinGW64，必須同時加上 `--mingw64` 與 `--experimental=force-mingw64`。若偏好微軟工具鏈，改安裝 Visual Studio 2022 Build Tools（勾選「Desktop development with C++」與 Windows SDK），並把這兩個旗標換成 `--msvc=latest`。

所有建置指令都必須加上 `--update-check=never`。在 uv 管理的 Python 3.13 上，Nuitka 預設的更新檢查會因 OpenSSL 問題以 `OPENSSL_Uplink ... no OPENSSL_Applink` 中止，看起來像編譯失敗，實際上是檢查階段就結束。

### 安裝建置工具

```powershell
uv sync
uv add --dev nuitka
```

### 建置 GUI 版

```powershell
uv run python -m nuitka `
  --mode=standalone `
  --mingw64 --experimental=force-mingw64 `
  --lto=yes --update-check=never --assume-yes-for-downloads `
  --enable-plugin=pyside6 `
  --windows-console-mode=disable `
  --windows-icon-from-ico=assets\app.ico `
  --include-data-files=assets\app.ico=assets\app.ico `
  --output-dir=build\nuitka `
  --output-filename=FireWallExcelFinder.exe `
  --product-name=FireWallExcelFinder `
  --file-version=0.1.0 --product-version=0.1.0 `
  firewall_gui.py
```

### 建置 CLI 版

```powershell
uv run python -m nuitka `
  --mode=standalone `
  --mingw64 --experimental=force-mingw64 `
  --lto=yes --update-check=never --assume-yes-for-downloads `
  --windows-console-mode=force `
  --windows-icon-from-ico=assets\app.ico `
  --output-dir=build\nuitka `
  --output-filename=FireWallExcelFinder-cli.exe `
  --product-name=FireWallExcelFinder `
  --file-version=0.1.0 --product-version=0.1.0 `
  audit_firewall_ips.py
```

本次建置不處理程式簽署；正式散布前請另外以 `signtool` 簽署兩個 exe。
```powershell
signtool sign /n IsaacTestApp /tr http://timestamp.digicert.com /td sha256 /fd SHA256 "D:\PythonProjects\FireWallExcelFinder\build\nuitka\firewall_gui.dist\FireWallExcelFinder.exe"
```
```powershell
signtool sign /n IsaacTestApp /tr http://timestamp.digicert.com /td sha256 /fd SHA256 "D:\PythonProjects\FireWallExcelFinder\build\nuitka\audit_firewall_ips.dist\FireWallExcelFinder-cli.exe"
```
### 輸出結構

```text
build\nuitka\
├─ firewall_gui.dist\
│  ├─ FireWallExcelFinder.exe
│  ├─ assets\app.ico
│  ├─ python313.dll
│  ├─ PySide6\
│  │  ├─ *.dll
│  │  └─ qt-plugins\platforms\qwindows.dll
│  ├─ Qt6*.dll
│  └─ ...
└─ audit_firewall_ips.dist\
   ├─ FireWallExcelFinder-cli.exe
   ├─ python313.dll
   └─ ...
```

`*.build` 是編譯中繼檔，可刪除；`*.dist` 才是要散布的內容。

### 使用方式

- 將整個 `firewall_gui.dist` 或 `audit_firewall_ips.dist` 複製到目標電腦，雙擊其中的 exe。
- 不可只複製 exe：同資料夾的 DLL、`PySide6` 與 `PySide6\qt-plugins` 都是執行必要檔案。
- GUI 的 `targets.txt` 與報告預設寫入 `%LOCALAPPDATA%\FireWallExcelFinder`，因此程式可以放在任何位置（包含 `Program Files`），不需要系統管理員權限。
- 第一次啟動若資料目錄沒有 `targets.txt`，GUI 會先在路徑欄位顯示預設位置；編輯規則後按「儲存」即可建立。
- CLI 仍以目前工作目錄解析 `--dir` 與 `--target` 的相對路徑。從捷徑啟動時請傳絕對路徑，或把捷徑的「開始位置」設為要掃描的資料夾。
- 控制檔與日誌位置不變：`%LOCALAPPDATA%\FireWallExcelFinder\logging.ini` 與 `logs\firewall_excel_finder.log`。

### 注意事項

- **未簽章**：Windows SmartScreen 會顯示「未知的發行者」，防毒軟體也可能誤報；簽署後才會改善。
- **GUI 版沒有主控台輸出**：`--windows-console-mode=disable` 會關閉 console，診斷請看日誌檔或把 `logging.ini` 的 `ui` 調成 `INFO`／`DEBUG`。
- **LTO**：`--lto=yes` 是正式產出的必要條件；若只是排查編譯問題，可暫時改成 `--lto=no`，確認無誤後再改回。
- **整包更新**：改版時請整包替換 dist 資料夾，不要只覆蓋 exe，以免 DLL 與 Qt 外掛版本不一致。
- **路徑長度**：解壓到較短路徑（例如 `C:\Tools\FireWallExcelFinder`）可避免 Windows 長路徑與防毒掃描造成的問題。
- **建置機與目標機**：standalone 只保證同為 Windows x64；不要複製 `.build` 目錄，也不要期待目標機有 Python 環境。