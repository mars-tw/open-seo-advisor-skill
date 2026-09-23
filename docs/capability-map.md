# 能力地圖（Capability Map）

一頁看懂 Open SEO Advisor 目前有什麼、各自的實作狀態、怎麼呼叫。這是給
使用者與貢獻者的權威總覽——若與其他文件敘述衝突，以本表為準。

狀態只說明程式能力，不代表某個網站的 SEO 成效。公開的茶屋與工筆網址是單頁
敘事展示，沒有可用來證明收錄、非品牌搜尋流量或 AI 引用的數據；建站工作流也不是
一鍵產生可收款商店。逐頁驗收標準見[網站品質](website-quality.md)。

## 狀態圖例

- ✅ **implemented**：核心邏輯已實作、有測試、可實際產出結果。
- 🧪 **mock/plan-only**：流程可完整跑（免金鑰），但真實花錢/寫入/發布動作
  一律停在計畫或用 mock，不會實際執行。
- 🚧 **skeleton**：只有介面/prompt 模板，執行邏輯待後續版本。

## 分類（Taxonomy）

### 新增：Website Builder（v0.4.0）

| 能力 | 狀態 | 使用方式與範圍 |
|---|---|---|
| 引導式客製建站 | 技能工作流 | 依 `SKILL.md` 與 `docs/website-*.md`，agent 依品牌需求實作頁面、素材、功能與驗收；能否產圖、部署取決於宿主工具與帳號，CLI 不會代做 |
| 離線網站骨架 | ✅ | `website init/build/demo`：sales／shop／experience 的可編輯起點；預設文案、假資料與展示互動不能當成正式站內容或真實收款 |
| 離線檢查 | ✅ | `website check --site DIR`：JSON；exit 0 基線、2 草稿、1 錯誤。未量測現場 LCP、收錄、非品牌搜尋曝光或 AI 引用 |
| 免費額度部署 | 設定產出＋agent 引導 | CLI 產生 Workers Static Assets／Firebase Hosting／Cloud Run 設定；不自動登入、部署或開 Billing |
| GPT 網站素材 | agent 真工具產圖 | CLI 只列 prompt 與待補素材；內建 GPT image 優先，無工具就如實列待補，API 路徑另計費 |
| 收款商店 | agent 客製整合 | CLI 的示範 cart 不收款，外部 checkout 為逐商品連結；完整後端需另實作與交易測試 |

專案的能力分三層，避免「模式 / 模組 / 統籌器」混淆：

### A. 核心 SEO 模式（Core Modes）

| 能力 | 狀態 | CLI | 說明 |
|---|---|---|---|
| 顧問 Consultant | ✅ | `seo-advisor audit consultant --url <url>` | 對可爬取的指定範圍做技術 SEO 健檢，產出 Finding、健康分數與報告；分數不代表排名或 Search Console 成效 |
| 文章寫手 Content Writer | ✅ | `seo-advisor write --topic <主題>` | LLM brief→outline→draft→QA；免金鑰用 `--llm-provider mock` |
| 工程師 Engineer | ✅（robots/sitemap/canonical）/ 🚧（hreflang/結構化資料/redirect/CWV） | `seo-advisor fix engineer/rollback` | 自動修復三種問題，dry-run 預覽 + 二次確認才寫入，有備份/回滾；其餘修復類型仍是規劃中 |
| 資安 Security | ✅ | `seo-advisor security audit` | 被動式資安掃描（暴露檔案/目錄列表/cloaking/HTTPS/HSTS/spam/CMS 版本）；暴露檔案/目錄列表/cloaking 需 `--confirm-authorized` 明確授權，不做任何攻擊性測試 |
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

若要展示「多頁 SEO 站」或「購物站」能力，驗收對應的獨立頁面、商品／分類路徑與
實際商務狀態。若要展示 SEO 成效，先有可收錄正式站、逐頁 metadata／標題／效能驗證，
再提供 Search Console 索引及非品牌查詢資料。AI 搜尋引用只可作具時間與查詢條件的
觀察，不能以品牌名搜尋截圖或 demo 分數替代。

## 誠實聲明

標 🧪 的能力，「分析」部分是真的，但「會花錢/寫入/發布的執行」目前一律停在
計畫或 mock，不會實際發生——這是刻意的安全設計（見各模組文件與
`docs/autopilot_mode.md`）。標 ✅ 的能力若需要付費 API（產圖、LLM 產文），
未提供金鑰時會自動降級為 mock 或給清楚的人話錯誤，不會靜默失敗。
