# AI 矩陣營運系統（AI Matrix Operating System）

把 AI 從「單一聊天工具」升級成一個可擴充、可分工、可追蹤、可跨行業套用的
**虛擬組織**。使用者只要提出一句目標，NORA 總控就會判斷情境、拆解任務、
派工給多位 AI 工作夥伴協作，最後整合成一份可執行交付物。

## 定位：上層統籌層

矩陣系統是整個技能的「上層統籌層」，底下把現有的專業模式當「引擎」。
**目前 26 個角色中，7 個（27%）已接上真實專屬引擎，其餘 19 個（73%）走通用
LLM 引擎**（`default_engine: generic_llm`，見 `matrix/assets/roles.yaml`）：

| 角色 | 專屬引擎 |
|---|---|
| **IRIS**（SEO） | 顧問模式引擎（`consultant`） |
| **MAYA / LUNA / ECHO / CODY**（內容類） | 文章寫手引擎（`content_writer`） |
| **JACK**（廣告） | Meta 廣告引擎（`meta_ads`） |
| **PIXEL**（產圖） | 產圖素材引擎（`image_material`） |
| 其餘 19 個角色（策略/財務/人資/法務/客服/營運…） | 通用 LLM 引擎（`generic_llm`） |

> 沒有專屬引擎不代表不能用——`generic_llm` 一樣能執行任務（免金鑰時走
> MockEngine，有金鑰時走 GenericLLMEngine），只是還沒有針對該角色職能客製
> 的專業邏輯（例如財務角色目前不會真的讀你的報表，而是用通用 LLM 生成建議）。
> 把更多角色接到專屬引擎是持續進行中的工作，見 `docs/roadmap.md`。

## 觸發方式

```bash
# 免金鑰示範（製造業新品上市情境）
seo-advisor matrix demo

# 一句目標，自動派工
seo-advisor matrix run --goal "推廣新款工業零件，增加海外 B2B 詢價" --industry 製造業

# 用有金鑰的 LLM 讓角色產出真實內容
seo-advisor matrix run --goal "..." --provider anthropic

# 查看所有 AI 工作夥伴
seo-advisor matrix roles
seo-advisor matrix role jack
```

## AI 工作夥伴（26 角色，資料驅動）

角色定義放在 `scripts/seo_advisor/matrix/assets/roles.yaml`（資料驅動，不為每個
角色寫 class），分五層 + 行業插件概念：

- **總控與管理層**：NORA（總控長）、ATLAS（策略）、NOVA（專案）、VERA（品質審核）、ORION（數據分析）
- **行銷與品牌層**：MAYA（社群）、IRIS（SEO）、JACK（廣告）、LUNA（品牌定位）、ECHO（公關）、PIXEL（視覺）
- **銷售與客戶層**：REX（業務開發）、SOPHIA（客戶成功）、TARA（客服）、CODY（銷售頁）、MIRA（CRM）
- **產品與營運層**：LEON（產品/頁面設計）、KAI（產品經理）、RINA（營運優化）、OTTO（自動化）、FINN（採購供應鏈）
- **財務/人資/法務/行政層**：GRACE（財務）、HERA（人資）、LEX（法務風險）、AMY（行政）、DOC（文件知識）

## 安全底線

矩陣系統沿用整個專案「安全優先」的一貫原則，並在路由層強制一條**通用升級
規則**：

> 任何任務只要含 `write / deploy / spend / publish / send`（中英文關鍵字，
> 例如「發布 / 寄送 / 花錢 / 投放 / 部署 / 上架 / 調整預算」），即使該角色
> 平常不需人工審核，也會被升級為 **需人工確認 + 只產計畫（plan / dry-run）**。

此外，涉及廣告預算（JACK）、法務（LEX）、財務數字（GRACE）、對外發布（ECHO）
的角色，在 `roles.yaml` 中就預設標記 `human_review_required: true`。交付報告
會清楚列出所有「需人工確認」的風險項目。

## NORA 標準運作流程

```
一句目標（TaskRequest）
  → NORA 選角色（select_roles：關鍵字 + 行業加權）
  → 拆解派工（build_assignments + 安全升級）
  → 各角色透過 engine 執行
  → 整合成 MatrixDeliverable（executive summary + 整合行動清單 + 風險）
  → 標記人工審核項目
  → 輸出 matrix-report.md / matrix-report.json
```

## 輸出

- `matrix-report.md`：可讀交付報告（各角色產出、整合行動清單、風險、下一步）。
- `matrix-report.json`：機器可讀的完整 MatrixDeliverable。
