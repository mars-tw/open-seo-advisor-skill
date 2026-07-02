# Changelog

本專案採用 [Semantic Versioning](https://semver.org/)。

## [0.1.2] - Unreleased

本版本源自與 CODEX（審核端）協作的全面架構/資安/新手體驗稽核，修正
稽核發現的問題，並完整實作 Content Writer Mode。

### 安全性修正

- **[P0]** 修正 `LocalArchiveConnector` 解壓 zip 檔案時的 zip slip /
  path traversal 漏洞（新增 `security/safe_archive.py`：
  `safe_extract_zip()` 逐項驗證解壓路徑，`resolve_inside_root()` 約束
  所有檔案存取在掃描根目錄內），並加上 zip bomb 防護（檔案數量／單檔／
  總解壓大小上限）。
- 新增 `SafetyPolicy`（`models.py`）：把 `docs/connector_contract.md`
  定義的資安原則（dry-run、capabilities、SSRF 防護）從文件變成建構子
  強制要求的參數，所有 Connector 都需接受並遵守。
- `HTTPConnector` 補上：robots.txt 遵循（`security/robots_policy.py`）、
  請求速率限制（`security/rate_limiter.py`）、SSRF 基本防護
  （`security/network_policy.py`，拒絕 localhost/私有網段/雲端 metadata
  IP）、sitemap 爬取範圍限制（不會照單全收爬取外部網域的 URL）、
  redirect 導致的 host 變更會正確更新允許爬取範圍。
- URL 正規化拒絕含帳號密碼的網址（例如 `https://user:pass@example.com`），
  避免憑證意外外洩到報告或日誌。

### 修正

- 修正 `WebsiteConnector.fetch_url()` 抽象簽名與實際呼叫不一致的問題。
- 修正 duplicate title 檢查的 evidence 錯誤：原本 `affected_urls` 沒有
  真的過濾出重複標題的頁面，而是回傳前 20 個任意頁面。
- 修正 demo 模式與 scoring 設定的打包問題：原本讀取
  `scripts/tests/fixtures/`、`config/scoring.yaml`，這些路徑在正式
  wheel 安裝後不存在；改用套件內建資產（`demo_assets/`、
  `config_assets/`）+ `importlib.resources`，並新增
  `test_wheel_packaging.py` 用實際建置 wheel 驗證。
- `scan_runner.py` 新增 preflight 連線檢查：網站完全連不上（DNS/連線/
  逾時失敗）時拋出清楚錯誤，不再產出一份空洞卻顯示「掃描完成」的報告。

### 新增

- **Content Writer Mode 完整實作**（`scripts/seo_advisor/writers/`）：
  - `LLMProvider` 抽象層：`AnthropicProvider`、`OpenAIProvider`、
    `LocalProvider`（Ollama，免費）、`MockProvider`（測試/離線試玩用）。
  - brief → outline → draft → QA 四階段流程（`pipeline.py`）。
  - 程式化品質檢查（`quality.py`）：單一 H1、低品質 AI 內容起手式、
    YMYL 關鍵字偵測，併入 LLM QA 結果。
  - CLI 指令 `seo-advisor write`，支援 `--llm-provider mock` 免 API
    金鑰試玩。
- 新增 noindex / X-Robots-Tag 檢查（`analyzers/technical.py`）。
- 新增本地 HTML 編碼偵測（`encoding_utils.py`），支援 Big5/Shift_JIS/
  GBK 等非 UTF-8 網站，避免中日韓文字被誤判為缺少內容。
- `scoring.py` 讀取 `config/scoring.yaml` 的 `category_weights`，
  計算加權後的網站健康分數。
- 白話報告加上「已檢查範圍內」措辭與具體問題（sitemap/canonical/
  noindex 等）的白話說明對照表。
- CI 新增跨平台測試矩陣驗證 wheel 打包正確性。

## [0.1.1] - Unreleased

### Added（新手體驗優化）

- `QUICKSTART.md`：5 分鐘上手指南，不要求先懂 Python 或 SEO。
- `install.ps1` / `install.sh`：一鍵安裝腳本，自動偵測 Python、建立
  虛擬環境、安裝套件並驗證安裝結果。
- `docs/install-troubleshooting.md`：常見安裝問題排解。
- `docs/glossary-for-beginners.md`：SEO 術語白話對照表（sitemap、
  canonical、robots.txt 等，用生活化比喻解釋）。
- CLI 互動精靈（`seo-advisor` / `seo-advisor start`）：不帶參數執行時
  用問答方式引導完成掃描，不需要記任何指令參數。
- `seo-advisor demo`：不需要輸入任何網址，直接用內建範例資料產生
  完整報告，方便新手在掃描自己的網站前先了解報告長相。
- URL 自動正規化（`url_utils.py`）：使用者輸入 `example.com` 會自動補上
  `https://`，不再要求手動輸入完整網址格式。
- 人話錯誤訊息（`errors.py`）：連線逾時、網址錯誤、檔案不存在等常見
  錯誤，預設顯示可理解的說明與下一步建議，而非 Python traceback；
  加上 `--debug` 才顯示完整技術細節。
- 白話文報告層（`beginner_report.py` → `report-beginner.md`）：用「房屋
  健檢」比喻解釋網站健康分數與 P0-P3 優先順序，附上「最該先處理的
  3 件事」，供非技術人員（老闆、客戶）閱讀。
- CLI 進度提示：掃描過程顯示「第 X/4 步」階段性文字，讓使用者知道
  工具正在運作而非卡住。
- 報告輸出改為固定檔名（`report-beginner.md` / `report.md` /
  `report.json`），不再使用隨機 ID 檔名，方便新手直接找到檔案。
- 修正孤兒頁（orphan page）誤判：單頁網站的唯一頁面不再被誤判為孤兒頁。

## [0.1.0] - Unreleased

### Added

- 專案骨架、SKILL.md、文件（architecture / modes / connector contract /
  content writer guide / i18n guide / roadmap）。
- Finding / Report / Connector 的 JSON Schema。
- `WebsiteConnector` 抽象介面，實作 `HTTPConnector`、`LocalArchiveConnector`。
- 顧問模式（Consultant Mode）核心：技術面 crawler（robots.txt / sitemap /
  canonical / title・meta・H1 / 內外連結 / 狀態碼）、scoring、
  Markdown + JSON 報告產出。
- CLI 入口（`seo_advisor.cli`）與五大模式路由骨架（工程師／資安／文章寫手／
  外掛開發模式先提供 prompt 模板與介面，執行邏輯留待後續版本）。
- 基本測試與範例設定。

### 尚未實作（規劃於後續版本，見 `docs/roadmap.md`）

- Engineer Mode 的自動修復（fixers）。
- Security Mode 的主動掃描邏輯。
- Content Writer Mode 的 LLM 呼叫整合。
- Plugin Dev Mode 的 WordPress 外掛 scaffold。
- SSH / Git / WordPress API / Cloudflare / cPanel connector。
