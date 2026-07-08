# 能力地圖（Capability Map）

一頁看懂 Open SEO Advisor 目前有什麼、各自的實作狀態、怎麼呼叫。這是給
使用者與貢獻者的權威總覽——若與其他文件敘述衝突，以本表為準。

## 狀態圖例

- ✅ **implemented**：核心邏輯已實作、有測試、可實際產出結果。
- 🧪 **mock/plan-only**：流程可完整跑（免金鑰），但真實花錢/寫入/發布動作
  一律停在計畫或用 mock，不會實際執行。
- 🚧 **skeleton**：只有介面/prompt 模板，執行邏輯待後續版本。

## 分類（Taxonomy）

專案的能力分三層，避免「模式 / 模組 / 統籌器」混淆：

### A. 核心 SEO 模式（Core Modes）

| 能力 | 狀態 | CLI | 說明 |
|---|---|---|---|
| 顧問 Consultant | ✅ | `seo-advisor audit consultant --url <url>` | 技術 SEO 全站健檢，產出 Finding + 健康分數 + 白話報告 |
| 文章寫手 Content Writer | ✅ | `seo-advisor write --topic <主題>` | LLM brief→outline→draft→QA；免金鑰用 `--llm-provider mock` |
| 工程師 Engineer | 🚧 | （規劃中） | 自動修復 sitemap/canonical/hreflang 等，dry-run diff |
| 資安 Security | 🚧 | （規劃中） | 被動式資安掃描（暴露檔案/HTTPS/CMS 版本） |
| 外掛開發 Plugin Dev | 🚧 | （規劃中） | WordPress SEO 外掛 scaffold |

### B. 行銷模組（Marketing Modules）

| 能力 | 狀態 | CLI | 說明 |
|---|---|---|---|
| Meta 廣告 | 🧪 | `seo-advisor ads audit/plan/demo` | 廣告診斷 + dry-run 計畫；實際代操（動用預算）預設全鎖 |
| 產圖素材 Image | ✅（產圖需金鑰） | `seo-advisor image generate/demo/from-content` | 合規前置檢查 + 多變體；免金鑰用 `--provider mock` |
| 成長行銷 Growth | ✅ | `seo-advisor growth utm/cro/analytics/demo` | UTM 歸因、CRO 落地頁、跨渠道成效（Google 來源 read-only，無金鑰用 mock） |
| 電商 Ecommerce | ✅ | `seo-advisor ecommerce audit/demo` | Amazon/電商 listing 健檢（純邏輯免金鑰） |

### C. 統籌器（Orchestrators）

| 能力 | 狀態 | CLI | 說明 |
|---|---|---|---|
| AI 矩陣營運系統 Matrix | 🧪 | `seo-advisor matrix run/demo/roles` | NORA 派工 26 角色；7 個（27%）已接真實專屬引擎（consultant/content_writer/meta_ads/image_material），其餘 19 個走 generic_llm，詳見 `docs/ai-matrix-os.md` |
| 一鍵代操 Autopilot | ✅（分析）/ 🧪（花錢動作） | `seo-advisor auto <url>` / `auto-demo` | 網址目標會**真的跑一次快速 SEO 健檢**（Consultant）；產圖/產文/廣告等會花錢的動作仍停在計畫，經一次同意閘門 |

### D. 共用知識庫

| 能力 | 狀態 | 說明 |
|---|---|---|
| 行銷方法論知識庫 | ✅ | 4 領域 50 條中性化蒸餾檢核原則（`knowledge/methodology.yaml`） |

## 最推薦的入口

- **完全新手**：`seo-advisor auto <你的網址>`（一個指令）或直接 `seo-advisor`
  進精靈選第一個。
- **免金鑰試玩任何能力**：找對應的 `... demo` 指令（見上表）。

## 誠實聲明

標 🧪 的能力，「分析」部分是真的，但「會花錢/寫入/發布的執行」目前一律停在
計畫或 mock，不會實際發生——這是刻意的安全設計（見各模組文件與
`docs/autopilot_mode.md`）。標 ✅ 的能力若需要付費 API（產圖、LLM 產文），
未提供金鑰時會自動降級為 mock 或給清楚的人話錯誤，不會靜默失敗。
