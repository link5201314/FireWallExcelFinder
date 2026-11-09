# FireWallExcelFinder

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