# 01: 單一 IPv4 位址的離線掃描流程

**What to build:** 使用者能以 CLI 指定目標規則與 Excel 掃描目錄，掃描 `.xlsx` 活頁簿並在 Console 查看單一 IPv4 位址的命中及摘要。

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] CLI 可指定掃描目錄及目標規則檔，並提供規格定義的預設值。
- [ ] 預設只掃描指定目錄第一層；以低記憶體唯讀方式檢查所有工作表與儲存格，略過 Excel 暫存鎖定檔及符號連結。
- [ ] 可解析單一 IPv4 目標與儲存格中的單一 IPv4 位址，並在命中時顯示檔案、工作表、列欄座標及掃描摘要。
- [ ] 掃描完全在本機執行，不呼叫網路服務；以 CLI 外部行為測試命中及未命中情境。