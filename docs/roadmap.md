# Roadmap

## v0.1.0（MVP）

- [x] 專案骨架、`SKILL.md`、README、LICENSE（Apache-2.0）、
      CONTRIBUTING、SECURITY、CODE_OF_CONDUCT。
- [x] `config/`：defaults、scoring、sources、industry_profiles、
      locale_profiles。
- [x] `schemas/`：finding、report、connector 的 JSON Schema。
- [x] `WebsiteConnector` 抽象介面（`connectors/base.py`）。
- [x] `HTTPConnector`：純 HTTP 爬取，唯讀，任何公開網站可用。
- [x] `LocalArchiveConnector`：本地原始碼包/目錄掃描。
- [x] 技術面 crawler：狀態碼、redirect、robots.txt、sitemap.xml、
      canonical、title/meta/H1、內部連結、noindex。
- [x] `scoring.py`：P0-P3 排序、priority_score 計算。
- [x] `report.py`：Markdown + JSON 報告產出。
- [x] CLI 入口與模式路由骨架（Consultant Mode 可完整執行，其餘四個
      模式提供 prompt 模板與介面定義，執行邏輯留待後續版本）。
- [x] 基本測試（technical.py / scoring.py / report.py）與範例設定。

## v0.1.1（新手體驗優化）

- [x] 一鍵安裝腳本（`install.ps1` / `install.sh`）、`QUICKSTART.md`。
- [x] 互動精靈（`seo-advisor start`）、demo 模式（`seo-advisor demo`）。
- [x] URL 自動正規化、人話錯誤訊息（`--debug` 才顯示技術細節）。
- [x] 白話文報告（`report-beginner.md`，房屋健檢比喻）。
- [x] `docs/glossary-for-beginners.md` 術語對照表。

## v0.1.2（架構與資安稽核修正，與 CODEX 協作稽核後完成）

- [x] 修正 `LocalArchiveConnector` 的 zip slip / path traversal 漏洞
      （`security/safe_archive.py`），加上 zip bomb 防護。
- [x] `SafetyPolicy`：把 connector 資安原則（dry-run、capabilities、
      SSRF 防護）從文件變成程式碼約束（`models.py`）。
- [x] `HTTPConnector` 補上 robots.txt 遵循、rate limit、sitemap scope
      過濾（不爬外部網域）、redirect host 追蹤、SSRF 基本防護。
- [x] URL 正規化拒絕含帳密的網址（避免憑證外洩）；`scan_runner.py`
      加上 site unreachable 偵測，避免對完全連不上的網站產出空洞報告。
- [x] 修正 demo 模式與 scoring 設定的打包問題：改用套件內建資產
      （`demo_assets/`、`config_assets/`）+ `importlib.resources`，
      並用實際 wheel 打包驗證（`test_wheel_packaging.py`）。
- [x] 修正 duplicate title 的 evidence 錯誤（原本沒有真的過濾重複組）。
- [x] 新增 noindex / X-Robots-Tag 檢查。
- [x] 本地 HTML 編碼偵測（`encoding_utils.py`，支援 Big5/Shift_JIS/GBK
      等非 UTF-8 網站，避免中日韓文字誤判）。
- [x] `scoring.py` 讀取 `category_weights` 計算加權健康分數。
- [x] 白話報告加上「已檢查範圍內」措辭與具體問題白話對照表。
- [x] **Content Writer Mode 完整實作**：`writers/` 模組，
      `LLMProvider` 抽象層（Anthropic / OpenAI / Local / Mock），
      brief → outline → draft → QA 四階段流程，
      CLI `seo-advisor write` 指令，程式化品質檢查
      （單一 H1、低品質 AI 內容起手式、YMYL 關鍵字偵測）。

## v0.2.0

- [ ] Engineer Mode：`fixers/` 實作 robots.txt / sitemap / canonical /
      hreflang / 基礎 schema 的自動修復，含 dry-run diff 預覽。
- [ ] Security Mode：`analyzers/security.py` 實作被動式掃描
      （暴露檔案、目錄列表、HTTPS/TLS 檢查、CMS 版本比對）。
- [ ] `SSHConnector`（唯讀優先，寫入功能需明確開啟）。
- [ ] `GitRepoConnector`（產出可開 PR 的 branch + diff）。
- [ ] `WordPressAPIConnector`（唯讀：posts/pages/plugins/site health；
      寫入：需 Application Password）。
- [ ] Search Console API / GA4 Data API optional adapter。
- [ ] 產業 profile 加權邏輯串接進 `technical.py` 與 scoring。
- [ ] JavaScript SEO 檢查：raw HTML vs rendered HTML 差異比對
      （Playwright，optional dependency）。
- [ ] 結構化資料驗證（`analyzers/structured_data.py`）。

## v0.3.0

- [ ] `CloudflareConnector`：讀取 DNS/redirect/cache 規則，寫入需
      明確授權（redirect rules、cache rules、Pages 部署）。
- [ ] `CPanelConnector`（有限度部署能力）。
- [ ] IndexNow 發布整合（內容更新後主動通知支援的搜尋引擎）。
- [ ] hreflang / 多語 sitemap 產生器（Engineer Mode 擴充）。
- [ ] Report HTML/PDF 渲染（在 Markdown/JSON 基礎上新增可視化圖表：
      Impact x Effort matrix、URL 狀態分布、hreflang 矩陣）。
- [ ] Plugin Dev Mode：WordPress 外掛 scaffold 產生器（schema 產生器、
      內部連結建議工具、IndexNow 自動通知模組）。

## v1.0.0

- [ ] Connector API 穩定化（承諾向後相容）。
- [ ] Finding / Report schema 穩定化。
- [ ] 多套 CI fixture 網站（WordPress、Next.js、純靜態、SPA）供
      回歸測試。
- [ ] 社群貢獻指南完善、產業/語言 profile 覆蓋度擴大。
- [ ] Plugin 範本可直接發布至 WordPress Plugin 目錄等級的完整度。

## 技術棧（維持不變的原則）

- **語言**：Python 3.10+（`Typer` CLI、`Pydantic` 資料模型、`httpx`
  非同步 HTTP、`BeautifulSoup`/`lxml` 解析、`Rich` 終端輸出、
  `pytest` 測試）。
- **可選增強，非必要依賴**：`Playwright`（JS 渲染檢查）、
  Lighthouse CLI（Core Web Vitals，本地執行不需要 API key）。
- **不綁定付費服務**：Search Console、GA4、PageSpeed Insights、
  OpenAI、Anthropic、Cloudflare 一律做成 optional adapter，
  缺少對應 API key 時功能自動降級（略過該項檢查並在報告中註明），
  而不是報錯中止。
