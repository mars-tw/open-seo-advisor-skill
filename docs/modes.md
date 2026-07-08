# 核心 SEO 模式完整規格

> **想快速看全專案有什麼、各自實作到什麼程度？** 先看 `docs/capability-map.md`
> 能力地圖。本文件是**核心 SEO 模式**的詳細規格來源；行銷模組（Meta 廣告 /
> 產圖 / 成長 / 電商）、統籌器（Matrix / Autopilot）各有專屬文件，見能力地圖。

本文件是每個核心模式的完整規格來源。`prompts/*.md` 是給 LLM 使用的精簡版
system prompt，本文件是給實作者（人類或 AI coding agent）看的完整規格，
兩者需保持一致，修改其中一份時請同步檢查另一份。

---

## Consultant Mode

**狀態：v0.1.0 已實作核心。**

### 目標與適用情境

像資深 SEO 顧問一樣做全站健檢，輸出診斷、證據、優先順序與改善路線。
適用於新站檢查、流量下滑排查、改版前後對照、國際化擴張前的健檢、
技術 SEO 定期健檢。

### 觸發方式

- CLI：`seo-advisor audit consultant --url https://example.com`
- CLI：`seo-advisor audit consultant --source ./my-site`
- 自然語言：「幫我做全站 SEO 健檢」「分析這個網站為什麼流量掉」
  「這個網站 SEO 做得好不好」

### 檢查項目（v0.1.0 已實作 / 規劃中）

**已實作（technical.py）：**

- HTTP 狀態碼分布、redirect chain 長度與迴圈偵測
- `robots.txt` 存在性、語法、是否誤擋重要資源、是否宣告 sitemap
- `sitemap.xml` 存在性、格式、URL 數量上限（單檔 50,000 / 50MB）、
  是否為 sitemap index
- canonical 標籤：是否存在、是否指向自身、是否與 sitemap URL 一致、
  是否有多重/衝突宣告
- title / meta description / H1：存在性、長度、重複率
- 內部連結：孤兒頁偵測、點擊深度、重複 anchor text 比例
- noindex / nofollow 使用狀況
- HTTPS 使用、HTTP→HTTPS 轉址正確性

**規劃中（v0.2.0 起，見 `docs/roadmap.md`）：**

- Core Web Vitals（LCP/INP/CLS）：透過 PageSpeed Insights API（optional）
  或本地 Lighthouse CLI
- JavaScript SEO：raw HTML vs rendered HTML 差異比對（需 Playwright）
- 結構化資料完整性與 Rich Results 驗證
- 內容品質 / E-E-A-T 訊號（作者資訊、更新日期、來源引用）
- 國際化 hreflang 矩陣驗證
- Search Console / GA4 資料整合（optional adapter）
- 產業別加權檢查（依 `config/industry_profiles.yaml`）

### 輸出格式

Markdown + JSON 雙格式，結構：

1. Executive Summary（3-5 句話總結網站現況）
2. Site Health Score（0-100，依 finding 嚴重度加權計算）
3. Top Findings（前 10 筆，依 priority_score 排序）
4. 依 P0/P1/P2/P3 分組的完整 Finding 清單
5. Evidence Appendix（每筆 finding 的原始證據）

### 外部資料來源（optional adapter，非必要）

- Google Search Console API（Search Analytics / Sitemaps / URL Inspection）
- GA4 Data API
- PageSpeed Insights API / CrUX
- Lighthouse CLI（本地執行，不需要 API key）

---

## Engineer Mode

**狀態：v0.2.0 已上線 robots.txt / sitemap.xml / canonical 三種自動修復；
hreflang、結構化資料驗證、redirect、CWV 仍是規劃中（見 `docs/roadmap.md`）。**

### 目標與適用情境

直接修復技術 SEO 問題，產出 patch、diff、部署計畫與驗證結果。目前支援修
`robots.txt`（缺失/缺 Sitemap 宣告）、`sitemap.xml`（缺失時建立）、
canonical（移除頁面內多餘的重複標籤）；只支援本地原始碼包/目錄
（`--source`），不支援直接修改線上網站。

### 觸發方式

```bash
# 列出目前可自動修復的問題
seo-advisor fix engineer --source ./site

# 產出 dry-run 修復計畫（不寫入任何檔案）
seo-advisor fix engineer --source ./site --finding-id SEO-SITEMAP_MISSING-001 --site-url https://example.com

# 確認無誤後，真的套用（plan_id 從上一步的輸出取得）
seo-advisor fix engineer --source ./site --finding-id SEO-SITEMAP_MISSING-001 \
  --site-url https://example.com --apply --confirm "APPLY fix-SEO-SITEMAP_MISSING-001"

# 回滾（不會覆蓋你在套用之後又手動編輯過的檔案）
seo-advisor fix rollback --source ./site --backup <備份路徑> --apply --confirm "ROLLBACK <backup_id>"
```

自然語言：「直接幫我修 sitemap 和 canonical」（會被路由到上述指令）。

### 工作步驟

1. 偵測技術棧（static / Next.js / Nuxt / Laravel / Rails / WordPress /
   Shopify / headless CMS）。
2. 建立安全上下文：git branch、備份、dry-run、rollback plan。
3. 定位問題來源：URL → route → template/component → CMS setting。
4. 產出 Patch Plan，交人工確認。
5. 確認後才寫入（受 `config/defaults.yaml` 的 `safety.dry_run` 控管）。
6. 執行測試與 re-crawl 驗證。
7. 輸出 diff、驗證結果、回滾方式。

### 可修項目與依據

- `robots.txt`：正確語法、sitemap 宣告、避免誤擋重要資源。
- `sitemap.xml`：UTF-8 編碼、`urlset`/`loc`/`lastmod`、單檔 50,000 URL
  或 50MB 上限、超過則用 sitemap index。
- canonical：模板邏輯修正、參數頁/分頁/HTTP-HTTPS 統一。
- hreflang：HTML head / HTTP header / XML sitemap 三種形式擇一貫徹，
  每頁需包含自己與所有語言變體，URL 需為完整絕對路徑。
- 結構化資料：Organization、BreadcrumbList、Article、Product、FAQ、
  LocalBusiness 等，依頁面實際可見內容產生。
- Redirect：301/302 正確使用、消除 chain 與迴圈、HTTP→HTTPS、www 統一。
- Core Web Vitals：圖片尺寸/格式、關鍵資源 preload、CSS/JS 拆分、
  defer/async、移除未使用 JS。

### 輸出格式

Patch Plan / Files Changed / Before-After Crawl Diff / Test Results /
Deployment Steps / Rollback Steps / Remaining Risks。

---

## Security Mode

**狀態：v0.2.0 規劃中，本版本先提供介面與 prompt。**

### 目標與適用情境

檢查與 SEO 直接相關的資安風險：被駭內容、垃圾內容注入、惡意重導、
敏感檔案外洩、過時 CMS、HTTPS 問題。**僅做非破壞性、被動式檢查**，
不進行任何攻擊性測試。

### 觸發方式

- CLI：`seo-advisor security audit --url https://example.com`
- 自然語言：「檢查有沒有 SEO spam、被駭重導、.env 外洩」

### 檢查項目

- 暴露檔案：`.env`、`.git/`、備份 zip、SQL dump、debug log 等常見路徑
  的公開可存取性檢查（僅發 GET 確認狀態碼，不下載/不利用內容）。
- 目錄列表：Apache/nginx directory index 是否對外開放。
- CMS 版本與已知過時風險（WordPress core/plugin/theme 版本比對公開資訊）。
- SEO spam 跡象：隱藏文字/連結、與 Google 垃圾內容政策相符的可疑模式。
- Cloaking 跡象：一般 User-Agent 與 Googlebot/Bingbot 模擬請求的內容差異。
- 惡意重導跡象：從搜尋結果點入才觸發的重導、行動裝置限定重導。
- HTTPS/TLS：憑證有效性、mixed content、HSTS、建議 TLS 1.2/1.3。
- Search Console 的 Security Issues / Manual Actions（optional，需 API）。

### 輸出格式

Severity（S0 Critical / S1 High / S2 Medium / S3 Low）、SEO Impact
（Indexing / Ranking / Trust / User Safety）、Evidence、Remediation
（短期封鎖 / 中期修補 / 長期監控）、是否需要 rotate 憑證。

---

## Content Writer Mode

**狀態：✅ 已完整實作（LLMProvider 抽象層 + brief→outline→draft→QA +
`seo-advisor write`，免金鑰用 `--llm-provider mock`）。**

詳見 `docs/content_writer_guide.md`。

### 目標與適用情境

呼叫 LLM（Anthropic Claude / OpenAI GPT / 本地模型皆可，透過 provider
adapter 抽象化）產出符合 SEO 權威指導原則的內容：brief、outline、draft、
metadata、schema、內部連結建議。

### 觸發方式

- CLI：`seo-advisor write --topic "best crm for agencies" --market US --lang en`
- 自然語言：「幫我寫一篇符合 SEO 標準的文章」

### 工作步驟

1. Intake：產業、受眾、語言、地區、搜尋意圖、品牌語氣、轉換目標。
2. Research：可選擇整合既有頁面內容、GSC 查詢資料、公開資料。
3. Brief：主要/次要搜尋意圖、讀者待完成任務、內容缺口。
4. Outline：H1/H2/H3、answer-first 結構、比較表、FAQ、內部連結規劃。
5. Draft：原創觀點、具體證據與案例、避免關鍵字堆砌。
6. Metadata：title/description/slug/OG/alt text 變體。
7. Schema：依頁型選用 Article/FAQPage/Product/HowTo/LocalBusiness。
8. QA：事實查核、YMYL 審查提示、重複度檢查、AI 痕跡自我檢查。

---

## Plugin Dev Mode

**狀態：v0.3.0 規劃中，本版本先提供介面與 prompt 模板。**

### 目標與適用情境

為 WordPress 等 CMS 開發 SEO 外掛或模組，例如結構化資料產生器、
內部連結建議工具、IndexNow 自動通知、hreflang 管理器。

### 觸發方式

- CLI：`seo-advisor plugin dev --cms wordpress --feature schema-generator`
- 自然語言：「幫我規劃一個 WordPress SEO schema 外掛」

### 工作步驟

1. 定義外掛需求與目標 CMS 版本。
2. 選擇架構：PHP plugin、admin UI、REST endpoints、WP-CLI command、
   cron hook。
3. 安全設計：capability check、nonce、輸入 sanitize、輸出 escape、
   prepared SQL statement、i18n。
4. 資料模型：options / post meta / custom table / transient cache。
5. 實作功能、撰寫測試（PHPUnit、WordPress Coding Standards）。
6. 打包：`readme.txt`、版本號、changelog、license、release zip。

### 輸出格式

Plugin PRD / File Tree / Security Checklist / API Routes /
Database Migration / Admin UI Spec / Test Plan / Release Plan。
