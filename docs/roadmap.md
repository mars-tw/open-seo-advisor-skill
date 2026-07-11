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

## v0.1.3 ～ v0.1.17（已發布，行銷模組、統籌層、深度稽核）

> 以下摘要自 `CHANGELOG.md` 各版本詳細記錄；本節目的是讓 roadmap 反映
> 真實進度，避免讀者誤以為專案只到 v0.1.2。完整細節請見 CHANGELOG。

- [x] **v0.1.3** Meta 廣告優化模式（`AdsProvider` 抽象層、`AdsSafetyPolicy`
      多重預算防護、dry-run 行動計畫）+ 產圖素材模式（`ImageProvider`
      抽象層、合規前置檢查、與 Content Writer 串接）。
- [x] **v0.1.4** AI 矩陣營運系統（統籌層）：26 個資料驅動角色、NORA 路由器、
      安全升級規則（高風險任務強制人工審核+plan-only）、mock/generic engine。
- [x] **v0.1.5** 成長行銷模組：UTM 歸因規劃、CRO 落地頁優化、跨渠道成效分析
      （`AnalyticsProvider` 抽象層，read-only）；矩陣角色行銷能力擴充。
- [x] **v0.1.6** 行銷方法論知識庫（中性化蒸餾，50 條檢核原則）+ 電商 Listing
      健檢模式。
- [x] **v0.1.7** 一鍵代操機器人（`seo-advisor auto`）：一個指令自動分析、
      一次知情同意閘門、白名單/黑名單安全邊界。
- [x] **v0.1.8** 紮實度強化：能力地圖、API 契約文件、CI wheel 打包驗證、
      依賴版本上限、provider 失敗路徑測試。
- [x] **v0.1.9** 新手 UX 優化：裸網域 bug 修正、信任文案統一、
      execution_mode 誠實標示。
- [x] **v0.1.10** 深度資安強化：SSRF redirect 繞過修復、回應大小上限改真
      串流防記憶體 DoS、sitemap billion laughs 防護、錯誤訊息 redact。
- [x] **v0.1.11** SEO 診斷實用度：canonical 跨網域、Open Graph、JSON-LD
      三項新檢查（含 www↔apex 正規化防誤報）。
- [x] **v0.1.12** 內容↔顧問串接：`write --from-report` 把顧問報告的 SEO
      缺口轉成針對性寫作 brief。
- [x] **v0.1.13** 廣告↔產圖串接：`image from-ads` 把素材疲勞問題轉成新
      素材方向 brief，含低信心閘門防止白花錢。
- [x] **v0.1.14** Autopilot 接真實引擎（consultant 先行）：網址目標會真的
      跑一次快速 SEO 健檢，不再只是 plan-only 摘要。
- [x] **v0.1.15** 新手指令收斂：精靈簡化為只問網址、懶人包零指令、進階
      指令保留給熟悉使用者但不對新手主動展示。
- [x] **v0.1.16** 全系統健康度大辯論：多立場交叉稽核，修正供應鏈可追溯性
      （Dependabot + pip-audit）、單次掃描重複請求去重、provider 錯誤處理
      系統性補強。
- [x] **v0.1.17** HTML 單次解析收斂、autopilot 安全閘門 CI 保險機制、
      方法論知識庫時效性標記、www 子網域漏爬修正。

## v0.2.0 ～ v0.2.7

- [x] **v0.2.0** Engineer Mode：`fixers/` 實作 robots.txt / sitemap /
      canonical 的自動修復，dry-run 預覽 + 二次確認才寫入，有備份/回滾。
      hreflang/結構化資料/redirect/CWV 仍是規劃中（見下方）。
- [x] **v0.2.1** Security Mode：`security_mode/` 實作被動式掃描（暴露檔案/
      目錄列表/cloaking 粗略比對/HTTPS/HSTS/mixed content/SEO spam/CMS
      版本暴露提示），探測性檢查需明確授權確認才會執行。惡意重導判斷、
      Search Console API 整合、CMS CVE 查詢仍是規劃中（見下方）。
- [x] **v0.2.2** `GitRepoConnector`：`--write-mode git-branch` 讓 Engineer
      Mode 的修復產出可開 PR 的 branch+commit，要求 working tree 乾淨、
      拒絕 `.gitignore`/submodule/detached HEAD 等不安全情境，未完成
      session 偵測與 repo-level lock。不支援自動 push/開 PR/遠端連線。
- [x] **v0.2.3** `SSHConnector`（唯讀，MVP 只做 `read_files`）：透過 SFTP
      讀取遠端網站靜態檔案，component-wise walk 拒絕 symlink jail escape，
      DNS rebinding 防護，讀取白名單/denylist。不做 `read_logs`/`write_files`/
      `run_commands`/密碼認證/jump host。首次引入 NORA×Grok 雙模型交叉辯論
      流程定案設計。尚未接進任何 CLI 指令（只有 connector 本身，見下方
      CLI 整合仍待規劃）。
- [x] **v0.2.5** SSHConnector 接進 CLI（`seo-advisor audit consultant
      --source ssh --ssh-host ... --ssh-confirm "CONNECT host:port"`）+
      `read_logs`（`allowed_log_paths` 白名單，與 `read_file()` 共用
      component-wise walk 防 symlink，log 讀取從尾端 tail 且有位元組數
      上限，`since` 時間篩選 MVP 尚未支援）。修正了既有 `list_urls()`/
      `fetch_url()` 的缺陷（未遞迴、未過濾不安全輸入、capabilities 未
      誠實回報 read_urls）。`write_files`/`run_commands` 仍不做（風險與
      Engineer Mode 的 direct 模式相當甚至更高，需要另一輪設計與審查）。
- [x] **v0.2.4** `WordPressAPIConnector`（唯讀：posts/pages + 公開頁面
      fetch）：透過 REST API 盤點內容，`capabilities()` 只回報
      `{"read_urls"}`。只支援 Application Password（可選匿名唯讀），
      REST 回傳的 `link` 一律視為 attacker-controlled，經 scope
      allowlist（path segment 邊界、www/apex 單層 pair）雙重過濾才能
      進入爬取流程；認證請求零 redirect；分頁/回應大小皆有硬上限。第二次
      NORA×Grok 雙模型交叉辯論。尚未接進 CLI；`plugins`/`site health`
      盤點、寫入（未來規劃獨立的 `write_content` capability，只做
      draft/revision，不直接 publish）留待後續版本。
- [ ] Search Console API / GA4 Data API optional adapter（`growth/providers/
      google.py` 目前僅骨架：建構檢查已就緒，實際 API 呼叫需要 OAuth 認證，
      尚未實作；無憑證時請用 `--provider mock` 試玩）。
- [x] **v0.2.6** Engineer Mode 擴充：新增 hreflang（六種問題偵測：缺
      self-reference/重複語言代碼/格式不合法/非互相對稱/授權範圍外/
      HTML+sitemap 混用）與 CWV 靜態線索（img 缺 width/height、單頁
      ≥3 個未使用 defer/async 的外部 script）兩種技術 SEO 檢查。新增
      `PatchPlan.plan_only` 機制：redirect chain 與 hreflang 修復皆為
      plan-only（涉及伺服器設定或業務層語言對應決策，超出 Engineer
      Mode 安全自動寫入的範圍，只產出具體建議文字）；CWV 只有
      `decoding="async"` 做真修復（只補完全沒有此屬性的 `<img>`，單頁
      修改量超過 50 個會自動降級為 plan-only）。CSS 拆分/圖片壓縮/
      Lighthouse 真量測仍不做（見下方）。
- [x] **v0.2.7** Security Mode 擴充：新增惡意重導/doorway page 偵測
      （`check_referrer_based_redirect`，比較無 Referer vs 帶 Google
      搜尋結果 Referer 時的最終導向網址，導向外部網域才給高 severity，
      同網域路徑差異保守處理）；`HTTPConnector` 新增 `extra_headers`
      建構子參數並限制 allowlist（只允許 Referer/Accept-Language）。
      CMS 已知 CVE/漏洞資料庫查詢重新確認維持不做真實查詢（版本偵測
      只是粗略字串比對、不是可靠指紋，錯誤比對成本高於不做），只加強
      finding 文案透明度（明確說明「這不是漏洞確認」）。**至此
      v0.2.0 roadmap 規劃的所有項目（Engineer/Security Mode 擴充、
      三個新 Connector）皆已完成。**
- [ ] 產業 profile 加權邏輯串接進 `technical.py` 與 scoring。
- [ ] JavaScript SEO 檢查：raw HTML vs rendered HTML 差異比對
      （Playwright，optional dependency）。
- [ ] 結構化資料驗證：v0.1.11 已實作 JSON-LD **存在性與語法正確性**檢查
      （`_check_structured_data`），本項指更完整的 Schema.org **型別與必要
      欄位**驗證（例如 `Product` 是否有 `price`/`availability`）。

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
