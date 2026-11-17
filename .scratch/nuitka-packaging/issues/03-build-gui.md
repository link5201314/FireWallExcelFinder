# 03: 建置 GUI standalone

**What to build:** 以 Nuitka 建置無主控台的 GUI standalone 版本，包含 PySide6 外掛、圖示與 LTO。

**Blocked by:** 01、02

**Status:** ready-for-agent

- [x] 使用 `--mode=standalone --enable-plugin=pyside6 --windows-console-mode=disable`。
- [x] 使用 `--mingw64 --experimental=force-mingw64`，並以 `--update-check=never` 避開 OpenSSL 更新檢查問題。
- [x] 使用 `--lto=yes` 與 `--assume-yes-for-downloads`。
- [x] 嵌入 `assets/app.ico` 並散布 `assets/app.ico`。
- [x] 產出 `build\nuitka\firewall_gui.dist\FireWallExcelFinder.exe`。
- [x] 從專案外的工作目錄啟動，視窗可開啟並完成掃描。
- [x] 日誌檔仍寫入 `%LOCALAPPDATA%\FireWallExcelFinder\logs`。
- [ ] 待簽署：以 `signtool` 處理 exe（本次不做）。
