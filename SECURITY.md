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

## 已知限制（有意識的分階段風險接受）

以下項目經過評估，判斷在目前的使用情境（單機 CLI、使用者掃描自己輸入的網址）
下風險可接受，暫不投入修復；若專案演進到常駐服務/多租戶情境，需重新評估。

- **SSRF 防護的 DNS 解析與實際連線之間存在理論上的 TOCTOU 窗口**：
  `ensure_host_allowed()` 做一次 DNS 解析檢查後，httpx 實際連線時會再獨立解析
  一次；理論上攻擊者可用短 TTL 網域在兩次解析間切換成內網/metadata IP 繞過
  檢查。這需要「攻擊者控制惡意網域 + 精準時間窗口」，在單機 CLI（操作者與
  潛在受害者是同一人）情境下沒有第三方跨信任邊界，暫不修復。
- **`LocalProvider`（連接本機 Ollama）未套用與 `HTTPConnector` 相同的 SSRF 檢查**：
  `OLLAMA_BASE_URL` 目前允許使用者自行設定，但這本來就是使用者自己要連的本機
  服務，且尚無間接輸入來源。若未來這個設定值可能來自不受信任的設定檔或多租戶
  情境，需要重新設計（不能直接套用預設拒絕私網的邏輯，否則會擋掉連 localhost
  Ollama 這個核心用途）。
