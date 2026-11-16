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