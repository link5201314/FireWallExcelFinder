# FireWallExcelFinder

## 離線掃描防火牆 Excel

掃描器以 IPv4 區間交集比對目標規則與 Excel 儲存格中的位址，支援單一 IPv4、完整範圍、同一 `/24` 的末碼簡寫範圍及 CIDR。執行時不連線至外部服務，並以唯讀方式逐格掃描 `.xlsx` 活頁簿。

```powershell
# 使用目前目錄與預設 targets.txt
uv run python audit_firewall_ips.py

# 指定 Excel 目錄、目標檔、遞迴掃描、工作表篩選及 CSV 報告
uv run python audit_firewall_ips.py --dir .\excel --target .\targets.txt --recursive --sheets 正式區 測試區 --output .\report.csv
```

目標檔每行一條規則，空白行及以 `#` 開頭的整行會忽略。格式錯誤的目標行會警告後略過。未指定報告檔時，命中明細與摘要輸出至 Console；指定 `.txt` 或 `.csv` 報告時，摘要仍輸出至 Console。加上 `--verbose` 可顯示命中儲存格的完整文字；預設只掃描指定目錄第一層，加上 `--recursive` 才會掃描子目錄。

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