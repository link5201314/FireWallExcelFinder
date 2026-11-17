# 02: 應用程式圖示

**What to build:** 產生 `assets/app.ico` 與 `assets/app-icon.png`，供 Nuitka 嵌入 exe 與 GUI 視窗使用；缺少圖示時不得影響啟動。

**Blocked by:** 無

**Status:** ready-for-agent

- [x] `assets/app-icon.png` 為 1024×1024、透明背景。
- [x] `assets/app.ico` 含 16、24、32、48、64、128、256 六種以上尺寸。
- [x] 設計在 16×16 仍可辨識（盾牌＋表格＋放大鏡）。
- [x] GUI 以 `resource_path("assets", "app.ico")` 設定視窗圖示，缺少檔案時靜默略過。
- [x] 建置指令以 `--windows-icon-from-ico` 與 `--include-data-files` 帶入圖示。
