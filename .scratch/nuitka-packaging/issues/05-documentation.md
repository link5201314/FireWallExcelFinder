# 05: 打包文件

**What to build:** 在 `README.md` 補上打包指令、輸出結構、使用方式與注意事項，並更新 `.gitignore`。

**Blocked by:** 03、04

**Status:** ready-for-agent

- [x] README 說明 MinGW64／MSVC 兩種編譯器選項與 Python 3.13 的實驗旗標。
- [x] README 說明 `--update-check=never` 的原因（OpenSSL Applink 錯誤）。
- [x] README 列出 GUI 與 CLI 的完整建置指令（含 `--lto=yes`、不簽署）。
- [x] README 說明 `build\nuitka` 輸出結構。
- [x] README 說明整包複製、資料位置、日誌位置與 CLI 相對路徑注意事項。
- [x] README 說明未簽章 SmartScreen、LTO 建置時間、x64 限定與整包更新。
- [x] `.gitignore` 加入 `*.build/`、`*.dist/`、`*.onefile-build/`。
