# 04: 建置 CLI standalone

**What to build:** 以 Nuitka 建置保留主控台的 CLI standalone 版本，功能與原始碼版一致。

**Blocked by:** 01

**Status:** ready-for-agent

- [x] 使用 `--mode=standalone --windows-console-mode=force`。
- [x] 使用 `--mingw64 --experimental=force-mingw64`、`--update-check=never` 與 `--lto=yes`。
- [x] 產出 `build\nuitka\audit_firewall_ips.dist\FireWallExcelFinder-cli.exe`。
- [x] 從專案外的工作目錄以絕對路徑執行，退出碼與報告內容正確。
- [x] 報告維持 UTF-8 BOM 與既有欄位。
- [x] 相對路徑維持目前工作目錄語意，並在 README 說明捷徑注意事項。
