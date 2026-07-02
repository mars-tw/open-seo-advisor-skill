# API 契約（給貢獻者）

這份文件是貢獻者要新增/修改模組時的內部契約速查。目標是讓你不用逐檔讀原始碼
就知道各層的介面長什麼樣、要遵守什麼。

## 抽象層總覽

專案有幾組平行的「provider / connector 抽象層」，設計精神一致（介面 + 具體
實作 + factory + mock），彼此不共用型別但心智模型相同：

| 抽象層 | 介面檔 | 具體實作 | mock |
|---|---|---|---|
| WebsiteConnector（爬取/檔案來源） | `connectors/base.py` | http / local_archive | — |
| LLMProvider（文字生成） | `writers/providers/base.py` | anthropic / openai / local | mock |
| ImageProvider（圖像生成） | `images/providers/base.py` | openai | mock |
| AdsProvider（廣告平台） | `ads/providers/base.py` | meta（read-only） | mock |
| AnalyticsProvider（成效資料，read-only） | `growth/providers/base.py` | ga4 / search_console / google_ads | mock |
| Engine（矩陣角色執行） | `matrix/engines/base.py` | generic_llm | mock |

**新增 provider 的規則（所有抽象層通用）：**

1. 繼承對應的 base 介面。
2. API 金鑰只從環境變數讀取；缺金鑰時拋出帶「請設定環境變數 X」的清楚錯誤。
3. 缺選配 SDK 時拋出帶「請 pip install X」的清楚錯誤。
4. 例外訊息**不得包含金鑰/token 原文**。
5. 加進對應的 `factory.py`，未知名稱要拋出列出可用選項的錯誤。
6. 附測試：至少涵蓋「缺金鑰」與「工廠未知名稱」兩條失敗路徑（見
   `tests/test_provider_failures.py` 的既有範例）。

## 安全型別

- `models.SafetyPolicy`：Connector 的資安約束（dry_run / allowed_capabilities /
  allow_private_network / respect_robots_txt / rate_limit）。任何寫入類方法
  需先 `require_capability()` 與 `require_write()`。
- `ads.models.AdsSafetyPolicy`：廣告代操的預算防護。高風險動作
  （增加預算/啟用/暫停活動）預設全鎖，需逐項明確開啟。
- `autopilot.safety`：一次同意的白名單/黑名單 + 確認字串驗證。
  `is_auto_executable()` 是唯一判斷「同意後可否自動執行」的入口，破壞性/
  不可回滾/critical 風險一律回 False。

## 報告輸出慣例

各模組寫出報告到 `--out` 目錄，慣例：

- 有白話層的模組：`*-beginner.md`（給非技術者）+ `*.md`/`*-report.md`
  （完整版）+ `*.json`/`*-report.json`（機器可讀）。
- 特殊產物：`cost-estimate.json`（autopilot）、`action-plan.json`（ads/autopilot）、
  `image-manifest.json`（image）。
- **heuristic / 自動推測性質的報告**，摘要要有「這是自動推測、非人工判定」的
  提醒（見 growth/ecommerce 報告）。

## 資料驅動資產（用 importlib.resources 讀取）

打包後必須存在的套件內資產（都已在 `pyproject.toml` 的 package-data 註冊，
新增時記得同步）：

- `matrix/assets/roles.yaml`：26 角色卡。
- `matrix/prompts/*.md`：generic engine prompt。
- `knowledge/methodology.yaml`：50 條中性化方法論。
- `config_assets/scoring.yaml`：健康分數權重。
- `demo_assets/**`：demo 用示範網站。

有一條測試（`tests/test_wheel_packaging.py`）會實際 build wheel 驗證這些資產
被打包——新增資產時請一併擴充它。

## 核心資料模型

- `models.Finding`：所有 SEO 檢查結果的統一格式（id/severity/impact/effort/
  confidence/recommendation/evidence）。
- `models.Report`：Consultant 報告。
- 各模組有自己的 report 型別（`CroReport`/`EcommerceReport`/`AdsReport`/
  `MatrixDeliverable`/`AutopilotDeliverable` 等），都是 Pydantic BaseModel，
  用 `model_dump(mode="json")` 序列化。

## 新增一個「模式/模組」的最小清單

1. `models.py`（Pydantic）+ 需要的 provider 抽象層。
2. 核心邏輯（analyzer / runner）。
3. `report.py`（Markdown + JSON）。
4. `cli.py`（Typer subapp），掛進 `seo_advisor/cli.py`，**一定要有 `demo` 子指令**
   讓人免金鑰試玩。
5. 若用到 enum Mode，加進 `models.Mode` 與 `router.py` 的 alias 與
   `_IMPLEMENTED_MODES`。
6. 測試（含 demo 產出、失敗路徑）。
7. 文件（`docs/<mode>.md`）+ 更新 `docs/capability-map.md`。
8. CI 的 demo smoke（`.github/workflows/ci.yml`）加一條。
