# 安全政策

## 使用範圍聲明

Open SEO Advisor 是一套**唯讀優先、需明確授權**的網站 SEO 診斷／修復工具。
使用者對本工具所執行的任何掃描、讀取或修改行為，**必須**是對自己擁有或已取得
明確授權的網站與主機進行。對未授權第三方網站進行掃描或利用本工具尋找漏洞，
不在本專案的預期用途範圍內，使用者需自行承擔法律責任。

## 回報漏洞

如果你在 Open SEO Advisor 本身的程式碼中發現安全性問題（例如：憑證可能外洩、
command injection、path traversal、SSRF 等），請**不要**開公開 issue，
而是透過以下方式私下回報：

- 於 GitHub repo 使用 **Private Vulnerability Reporting**（Security 分頁 →
  Report a vulnerability）。

請包含：問題描述、重現步驟、受影響版本、可能的影響範圍。我們會盡快確認並修補，
修補後會在 `CHANGELOG.md` 中致謝（除非你希望匿名）。

## 設計上的資安原則

- 預設 `read-only`、預設 `dry-run`，所有寫入/部署行為需要人工確認。
- 憑證只能來自環境變數、OS keychain 或當下輸入，不落地到報告或 log。
- Connector 的 `run_command` 走 allowlist，不允許任意 shell 指令。
- 對 production 環境的寫入操作，一律要求二次確認與可回滾方案。
