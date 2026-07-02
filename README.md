# Open SEO Advisor

> 開源、可攜、不綁定單一廠商的全域 SEO 顧問技能。蒸餾業界公認的 SEO 權威方法論
> 與 Google 官方標準，結合爬蟲與 LLM，協助任何產業、任何規模的網站做 SEO 健檢、
> 修復、內容產出與外掛開發。

[![CI](https://github.com/mars-tw/open-seo-advisor-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/mars-tw/open-seo-advisor-skill/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

> **第一次使用？不用懂程式，也不用懂 SEO。**
> 直接看 [`QUICKSTART.md`](QUICKSTART.md)，5 分鐘拿到你的第一份 SEO 健檢報告。

## 這是什麼

Open SEO Advisor 是一套設計給 [Claude Code](https://claude.com/claude-code) 之類
的 AI coding agent 使用的「技能（Skill）」，也可以獨立當作 CLI 工具使用。它把
「資深 SEO 顧問怎麼做網站健檢」「工程師怎麼修技術 SEO 問題」「資安人員怎麼檢查
SEO 相關風險」「SEO 內容編輯怎麼寫符合 E-E-A-T 的文章」「外掛工程師怎麼開發
WordPress SEO 外掛」這五種專業角色的方法論，蒸餾成可執行的檢查清單、報告格式
與程式碼。

## 七大模式

1. **顧問模式 Consultant** — 全站 SEO 健檢，產出診斷報告與 P0–P3 優先順序建議。
2. **工程師模式 Engineer** — 直接修復 sitemap、robots.txt、canonical、hreflang、
   結構化資料、Core Web Vitals 等技術問題。
3. **資安模式 Security** — 檢查與 SEO 相關的資安風險（外洩檔案、過時 CMS、
   垃圾內容注入、惡意重導、HTTPS 問題等）。
4. **文章寫手模式 Content Writer** — 呼叫 LLM（Anthropic Claude / OpenAI GPT /
   本地模型皆可）產出符合 SEO 權威指導原則的內容。
5. **外掛開發模式 Plugin Dev** — 為 WordPress 等 CMS 開發 SEO 相關外掛與模組。
6. **Meta 廣告優化 Meta Ads** — 診斷 Meta（Facebook/Instagram）廣告帳戶，
   產出優化建議與 dry-run 行動計畫。動用真實預算的操作受多重安全防護，預設全鎖。
7. **產圖素材 Image Material** — 為廣告/社群/文章產生圖像素材，圖像 provider
   可換（OpenAI / 未來可加其他），並有合規前置檢查。

已完整實作：Consultant、Content Writer、Meta Ads、Image Material。
詳細規格見 [`SKILL.md`](SKILL.md)、[`docs/meta_ads_mode.md`](docs/meta_ads_mode.md)、
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

## 設計原則

- **不綁定單一廠商**：所有付費 API（Search Console、GA4、PageSpeed Insights、
  OpenAI、Anthropic、Cloudflare…）都是 optional adapter，核心功能不依賴任何一個。
- **預設唯讀、預設 dry-run**：任何寫入或部署動作都需要人工確認。
- **可攜**：可接入 SSH、本地原始碼包／zip、Git repo、WordPress REST API、
  Cloudflare API、cPanel 等多種來源，透過統一的 `WebsiteConnector` 介面。
- **全球全產業**：涵蓋 B2B／B2C、電商／SaaS／在地服務／內容媒體／企業官網，
  並考慮多語言、多地區 SEO（hreflang、Local SEO）。

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

`--url` 可以省略 `https://`，工具會自動補上。掃描完成後會產出三份報告：
`report-beginner.md`（白話懶人包）、`report.md`（完整技術報告）、
`report.json`（機器可讀資料）。

看 [`docs/architecture.md`](docs/architecture.md) 了解整體架構，
看 [`docs/roadmap.md`](docs/roadmap.md) 了解目前實作進度與未來規劃。

## 貢獻

歡迎任何形式的貢獻！請先看 [`CONTRIBUTING.md`](CONTRIBUTING.md) 了解開發環境
設定與貢獻規範。回報問題或提出功能建議請開 [Issue](https://github.com/mars-tw/open-seo-advisor-skill/issues)。

## 授權

Apache License 2.0，詳見 [`LICENSE`](LICENSE)。歡迎 Fork、修改、再散布，
也歡迎提交 PR 貢獻新的 connector、analyzer、產業設定檔或語言在地化。
