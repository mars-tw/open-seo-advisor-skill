# Open SEO Advisor

免下載、免登入，直接體驗兩種敘事網站：

| 線上示範 | 可以體驗什麼 | 素材與本機預覽 |
|---|---|---|
| [一片葉的回家路](https://open-seo-advisor-demo.digimkt.workers.dev/) | 四幕旅程、點燈、倒帶與靜態閱讀 | [山嵐茶屋範例](examples/immersive-tea/README.md) |
| [一筆敬意｜工筆媽祖畫像](https://open-seo-gongbi-demo.digimkt.workers.dev/) | 五段作畫敘事、捲動畫筆、訪客落印 | [工筆畫像範例](examples/immersive-gongbi/README.md) |

工筆畫像先點「開始作畫動畫」再捲動，也可 [直接看勾線](https://open-seo-gongbi-demo.digimkt.workers.dev/#outline)。
茶站有故事首頁與獨立製作說明頁；工筆站是單頁互動示範。兩站皆使用 GPT 圖像，
不提供預約或收款。它們展示捲動敘事，
不代表多頁商店、已通過 Core Web Vitals、取得自然搜尋流量或被 AI 搜尋引用。

**公開示範站查核（2026-09-23）：**

| 實際讀回或量測 | 茶屋示範 | 工筆示範 |
|---|---|---|
| 收錄設定 | `noindex,follow` | `noindex,follow` |
| sitemap | 空檔案 | 未提供 |
| 修正前手機 Lighthouse 模擬 LCP | 11.0 秒，主圖 PNG | 2.11 秒，主標文字 |
| v0.5.0 部署後手機 Lighthouse 模擬 LCP | 1.29 秒，主圖 WebP | 1.05 秒，主標文字 |

Lighthouse 是特定網路與裝置條件下的實驗室結果，不能當作實際使用者的 Core Web Vitals。
這份快照說明公開示範目前只供體驗；新版本已讀回檔案並重測。兩站維持 `noindex`，
沒有可驗證的收錄、非品牌查詢或 AI 引用成果。

## 能做什麼，哪些仍須驗證

近期版本修正 SEO 健檢對 robots.txt／sitemap.xml 的誤判、頁內錨點造成的重複頁面，
以及部分語系環境的 shell 安裝錯誤；詳見 [更新紀錄](CHANGELOG.md)。

沉浸式動畫以「主角要做什麼、遇到什麼、訪客怎麼參與、最後改變什麼」設計。
範例《一片葉的回家路》有四張 GPT 場景、獨立透明主角、可倒帶的路徑與分幕環境變化，
訪客的點燈操作會影響後續畫面和結尾。背景不使用縮放動畫。

本衍生版本在原有 SEO 顧問能力上，加入銷售站、購物站、互動體驗站的建置工作流。
使用者說明品牌與目的，agent 引導設計故事分幕、用 GPT 產生圖文、實作網站、驗收並選擇
Cloudflare、Firebase Hosting 或 GCP Cloud Run。免費額度與帳務條件分別查核。

目前 CLI 提供離線建站骨架與技術檢查；完整網站需要 agent 按品牌實作頁面、內容、功能
與圖像。單頁示範不能代替商品頁、分類頁或實際結帳。每個重要頁面要核對獨特且準確的
title／meta description、清楚的主標與章節、可讀 HTML、內部連結與收錄設定；沉浸式
首屏尤其要量測 LCP。H2 沒有保證排名的固定數量或順序，結構應方便人閱讀。
建好站不等於搜尋引擎已收錄；搜尋曝光、非品牌查詢與 AI 引用須上線後另行觀察，
其中品牌名查詢不能充當 AEO 成效證據。

對外宣稱也依證據分級：交付「可建站」須有能直接開啟的適用頁面與功能；宣稱「SEO
技術基線已驗證」須逐頁檢查 metadata、標題、索引設定、內部連結與手機效能；宣稱
「SEO 成效」須有上線後的索引與 Search Console 非品牌查詢資料；若主張詢問或銷售改善，
還須提供對應的有效行動資料。
AI 搜尋引用只能記錄特定引擎、題目、日期與引用 URL 的觀察，不能保證重現。

支援 **Codex 與 [OpenCode](https://opencode.ai/zht)** 等能載入 `SKILL.md` 的 coding agent。
OpenCode 使用者可依 [安裝與使用指南](docs/opencode.md)，在網站專案執行：

```bash
git clone https://github.com/mars-tw/open-seo-advisor-skill.git .opencode/skills/open-seo-advisor
opencode
```

上述 clone 是獨立的技能 Git 副本；若要隨網站一起版控，請用指南中的 ZIP 安裝方式。
在 OpenCode 的 Build 模式輸入「請載入 open-seo-advisor 技能，帶我建立沉浸式 SEO／AEO 網站」。
指南也附可選的 `/seo-website` 指令與 GPT 產圖工具設定說明。

在已安裝技能的 Codex 輸入：

> 使用 $open-seo-advisor，帶我建立有 GPT 圖文與沉浸式滾動動畫的購物網站，優先用免費主機。

將完整資料夾放在宿主的 skills 目錄，例如 `~/.codex/skills/open-seo-advisor/`，重新開啟
工作階段。無 agent 也能用 Python 3.10+ 執行離線建站精靈：

```bash
python -m pip install -e ./scripts
seo-advisor website init --out ./my-site
python -m http.server 8080 --bind 127.0.0.1 --directory ./my-site/public
```

開啟 `http://127.0.0.1:8080`。CLI 產出可操作的靜態骨架、素材 prompt 清單與部署設定；
**真正 GPT 產圖、客製多頁、支付後端與部署由 agent 後續完成，CLI 不會自動執行。**
展示購物車不收款；正式店需驗證支付流程。`website check` 只檢查離線基線，不保證排名或 AI 引用。

[完整建站流程](docs/website-builder.md) · [GPT 素材](docs/website-assets.md) ·
[主機選擇](docs/website-hosting.md) · [商務流程](docs/website-commerce.md) ·
[山嵐茶屋示範](examples/immersive-tea/README.md)

保留 [mars-tw/open-seo-advisor-skill](https://github.com/mars-tw/open-seo-advisor-skill) 原作者
與 Apache-2.0 授權；以下既有稽核、內容與行銷能力繼續保留。

> 這是開源的網站健檢 CLI 與 coding agent 技能。離線 demo 可以免金鑰體驗；
> 真實網站仍需要逐頁內容、瀏覽器效能驗證及上線後的 Search Console 觀察。
> 產圖、進階 API、網域與交易可能產生費用，依選用的工具和服務計算。
>
> 想快速看全貌？先看 [`docs/capability-map.md`](docs/capability-map.md) 能力地圖。

[![CI](https://github.com/mars-tw/open-seo-advisor-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/mars-tw/open-seo-advisor-skill/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

> **第一次使用？**
> 裝好後可執行：`seo-advisor auto https://你的網站.com`。它會檢查可取得的頁面，
> 產出一份白話報告與待辦清單；未取得的資料、無法量測的體驗及搜尋成效須另行驗證。
> **預設只做分析，不呼叫付費 API，也不會改動你的網站**；
> 若之後有任何付費或寫入動作，一定先列明細、你同意一次才執行。想先看範例就跑
> `seo-advisor auto-demo`。完整步驟見 [`QUICKSTART.md`](QUICKSTART.md)。

## 這是什麼

Open SEO Advisor 是一套設計給 [Claude Code](https://claude.com/claude-code) 之類
的 AI coding agent 使用的「技能（Skill）」，也可以獨立當作 CLI 工具使用。它把
「SEO 技術檢查」「技術修復建議」「SEO 相關資安檢查」「內容草稿」與「WordPress
SEO 外掛開發」等工作流，整理成可執行的檢查清單、報告格式
與程式碼。

## 七大模式

1. **顧問模式 Consultant** — 全站 SEO 健檢，產出診斷報告與 P0–P3 優先順序建議。
2. **工程師模式 Engineer** — 在支援的檔案與站點來源中規劃並修復 sitemap、robots.txt、
   canonical、hreflang 等技術問題；效能與 Core Web Vitals 須在目標站另行量測複驗。
3. **資安模式 Security** — 檢查與 SEO 相關的資安風險（外洩檔案、過時 CMS、
   垃圾內容注入、惡意重導、HTTPS 問題等）。
4. **文章寫手模式 Content Writer** — 呼叫 LLM（Anthropic Claude / OpenAI GPT /
   本地模型皆可）產出符合 SEO 權威指導原則的內容。
5. **外掛開發模式 Plugin Dev** — 為 WordPress 等 CMS 開發 SEO 相關外掛與模組。
6. **Meta 廣告優化 Meta Ads** — 診斷 Meta（Facebook/Instagram）廣告帳戶，
   產出優化建議與 dry-run 行動計畫。動用真實預算的操作受多重安全防護，預設全鎖。
7. **產圖素材 Image Material** — 為廣告/社群/文章產生圖像素材，圖像 provider
   可換（OpenAI / 未來可加其他），並有合規前置檢查。

各模式的已實作功能、限制及需要的 API 見 [`docs/capability-map.md`](docs/capability-map.md)、
[`SKILL.md`](SKILL.md)、[`docs/meta_ads_mode.md`](docs/meta_ads_mode.md)、
[`docs/image_material_mode.md`](docs/image_material_mode.md)。

## 上層統籌層：AI 矩陣營運系統

在七大模式之上，還有一個 **AI 矩陣營運系統**（`seo-advisor matrix`）：
提出一句目標，NORA 總控就會判斷情境、派工給 26 位 AI 工作夥伴角色
（策略/行銷/銷售/產品/營運/財務/人資/法務/行政）協作，各角色盡量接到
上述已實作的模式引擎，最後整合成一份可執行交付物。任何高風險任務
（發布/花錢/部署等）會被強制升級為需人工確認且只產計畫。

```bash
seo-advisor matrix demo   # 免金鑰試玩
seo-advisor matrix run --goal "推廣新產品增加詢價" --industry 製造業
```

詳見 [`docs/ai-matrix-os.md`](docs/ai-matrix-os.md)。

## 成長行銷模組

補齊網路行銷團隊的完整能力鏈：**UTM 歸因、CRO 落地頁優化、跨渠道成效分析**
（`seo-advisor growth`），全部免金鑰可試玩。

```bash
seo-advisor growth demo                                  # UTM + CRO + 成效分析
seo-advisor growth utm --url https://example.com/promo --channels google,facebook,email
seo-advisor growth cro --url https://example.com/landing
seo-advisor growth analytics --provider mock
```

成效分析的 Google 資料來源（GA4/GSC/Google Ads）一律 read-only，無憑證時用
mock。詳見 [`docs/growth_marketing.md`](docs/growth_marketing.md)。

## 電商 Listing 健檢 + 行銷方法論知識庫

內建**中性化蒸餾**的行銷方法論知識庫（電商 / 付費廣告漏斗 / 內容品牌 /
成長駭客四領域共 50 條可執行檢核原則），並用電商領域原則做 Amazon / 電商
platform 的 listing 健檢：

```bash
seo-advisor ecommerce demo                          # 免金鑰示範
seo-advisor ecommerce audit --input listing.json    # 健檢自己的 listing
```

> **合規說明**：方法論知識庫萃取業界公開、廣泛認可的通用原則，轉成**不具名、
> 不含課程名或商標**的檢核清單，不宣稱與任何特定專家有關聯或代言。目的是讓
> 任何人**免費**就能用這些方法論自我健檢，不需買課或代操。詳見
> [`docs/methodology.md`](docs/methodology.md)、[`docs/ecommerce_mode.md`](docs/ecommerce_mode.md)。

## 設計原則

- **不綁定單一廠商**：所有付費 API（Search Console、GA4、PageSpeed Insights、
  OpenAI、Anthropic、Cloudflare…）都是 optional adapter，核心功能不依賴任何一個。
- **預設唯讀、預設 dry-run**：任何寫入或部署動作都需要人工確認。
- **可攜**：可接入 SSH、本地原始碼包／zip、Git repo、WordPress REST API、
  Cloudflare API、cPanel 等多種來源，透過統一的 `WebsiteConnector` 介面。
- **依站型調整**：B2B／B2C、電商／SaaS／在地服務／內容媒體與企業官網的
  內容、商務與搜尋需求不同；多語言或多地區站另驗證翻譯、hreflang 與當地資訊。

## 快速開始

### 新手：一鍵安裝 + 問答式精靈

```bash
# Windows（PowerShell）
.\install.ps1

# Mac / Linux
./install.sh
```

安裝完成後，直接執行：

```bash
seo-advisor
```

會用問答方式引導你完成第一次掃描，完整步驟見 [`QUICKSTART.md`](QUICKSTART.md)。

### 進階：直接下指令

```bash
cd scripts
pip install -e .
seo-advisor audit consultant --url example.com --out ./report
```

`--url` 可以省略 `https://`，工具會自動補上。掃描完成後會產出四份報告：
`report-beginner.md`（白話懶人包）、`report.md`（完整技術報告）、
`report.json`（機器可讀資料）、`report.html`（含 Impact x Effort matrix/
URL 狀態分布/hreflang 矩陣等圖表的視覺化報告，可用瀏覽器開啟或列印為 PDF）。

看 [`docs/architecture.md`](docs/architecture.md) 了解整體架構，
看 [`docs/roadmap.md`](docs/roadmap.md) 了解目前實作進度與未來規劃。

## 貢獻

歡迎任何形式的貢獻！請先看 [`CONTRIBUTING.md`](CONTRIBUTING.md) 了解開發環境
設定與貢獻規範。回報問題或提出功能建議請開 [Issue](https://github.com/mars-tw/open-seo-advisor-skill/issues)。

## 授權

Apache License 2.0，詳見 [`LICENSE`](LICENSE)。歡迎 Fork、修改、再散布，
也歡迎提交 PR 貢獻新的 connector、analyzer、產業設定檔或語言在地化。
