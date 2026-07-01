# 架構總覽

## 設計哲學

Open SEO Advisor 把「資深 SEO 顧問／工程師／資安人員／內容編輯／外掛工程師」
的專業判斷拆解成三層：

1. **Connector 層**：負責「怎麼拿到網站的資料」（HTTP 爬取、SSH、原始碼包、
   CMS API、CDN API），對上層完全隱藏底層差異。
2. **Analyzer / Fixer / Writer 層**：負責「怎麼判斷問題、怎麼修、怎麼寫」，
   輸出統一的 `Finding` 物件或 `PatchPlan` / `ContentDraft`。
3. **Report / CLI 層**：負責「怎麼呈現給人看、怎麼讓人確認執行」。

這樣設計的目的：任何人想貢獻「支援某個新 CMS」或「支援某個新產業的檢查項目」，
都只需要在對應層新增一個模組，不需要改動其他層。

## 目錄結構

```text
open-seo-advisor-skill/
  SKILL.md                     # 技能入口，定義觸發詞、安全前提、模式總覽
  README.md
  LICENSE                      # Apache-2.0
  CHANGELOG.md
  SECURITY.md
  CONTRIBUTING.md
  CODE_OF_CONDUCT.md

  config/                      # 使用者可覆寫的設定
    defaults.yaml              # 爬蟲/渲染/輸出/安全 預設值
    scoring.yaml               # P0-P3 定義、Impact/Effort 量表、分類權重
    sources.yaml                # 檢核邏輯所依據的官方文件出處（供社群查核）
    industry_profiles.yaml     # 電商/SaaS/在地服務/媒體/企業官網 差異化檢查
    locale_profiles.yaml       # 語言/地區設定，hreflang 規則

  prompts/                     # 各模式的 system prompt 模板
    router.md
    consultant.md
    engineer.md
    security.md
    content_writer.md
    plugin_dev.md
    reviewer.md

  schemas/                     # JSON Schema，作為跨模組/跨語言的資料契約
    finding.schema.json
    report.schema.json
    connector.schema.json

  docs/                        # 本目錄
    architecture.md
    modes.md
    connector_contract.md
    content_writer_guide.md
    i18n_seo_guide.md
    roadmap.md

  scripts/
    pyproject.toml
    seo_advisor/
      cli.py                  # Typer CLI 入口
      router.py               # 模式路由
      crawler.py              # 技術面爬蟲（狀態碼/robots/sitemap/canonical/連結）
      scoring.py              # Finding → 優先順序排序
      report.py               # Finding[] → Markdown/JSON 報告
      models.py               # Pydantic 資料模型（Finding, Report, ...)
      connectors/
        base.py               # WebsiteConnector 抽象介面
        http.py               # 純 HTTP 爬取（唯讀，任何網站都可用）
        local_archive.py      # 本地原始碼包 / 解壓後的專案目錄
        ssh.py                # SSH/SFTP（v0.2 起實作）
        git_repo.py           # Git repo（v0.2 起實作）
        wordpress_api.py      # WordPress REST API（v0.2 起實作）
        cloudflare.py         # Cloudflare API（v0.3 起實作）
        cpanel.py             # cPanel（v0.3 起實作）
      analyzers/
        technical.py          # 技術 SEO 分析（Consultant Mode 核心）
        content.py            # 內容/E-E-A-T 分析（v0.2 起擴充）
        structured_data.py    # 結構化資料驗證（v0.2 起擴充）
        security.py           # 資安相關分析（v0.2 起實作）
      fixers/                 # Engineer Mode 的自動修復邏輯（v0.2 起實作）
      writers/                # Content Writer Mode 的 LLM 呼叫邏輯（v0.2 起實作）
      plugins/wordpress/      # Plugin Dev Mode 的 WordPress scaffold（v0.3 起實作）
    tests/
      fixtures/               # 測試用的假網站 HTML
      test_crawler.py
      test_scoring.py
      test_report.py

  examples/
    reports/                  # 範例輸出報告
    configs/                  # 範例設定檔
```

## 核心資料模型

### Finding

所有模式的檢查結果都收斂成統一的 `Finding` 物件（見
`schemas/finding.schema.json`），欄位包含：

- `id` / `title` / `mode` / `category`
- `severity`（P0-P3）、`impact`（1-5）、`effort`（1-5）、`confidence`（0-1）
- `affected_urls`、`evidence`（實際觀察到的資料，如 HTTP status、canonical 值）
- `recommendation`、`validation`（驗證修復是否成功的步驟）
- `owner`（建議由哪個模式/角色處理）

### Report

`Finding[]` 經過 `scoring.py` 排序後，由 `report.py` 組成 `Report`
（見 `schemas/report.schema.json`），包含 Executive Summary、
Site Health Score、Top Findings、依 severity 分組的完整清單、
Evidence Appendix。

### 優先順序邏輯

```text
priority_score = impact * confidence / effort
```

排序規則：先依 `severity`（P0 > P1 > P2 > P3）分組，同組內再依
`priority_score` 由高到低排序。權重可在 `config/scoring.yaml` 調整。

## Connector 抽象層

見 `docs/connector_contract.md`。核心精神：**上層 analyzer 完全不知道資料是
從 HTTP 爬來的、還是從 SSH 讀檔案讀來的、還是從 WordPress API 拿到的**，
一律看到相同的 `PageSnapshot` / `FileRecord` 介面。

## 模式路由

`router.py` 根據：

1. 使用者是否用明確指令（如 `/seo-audit consultant`）。
2. 若是自然語言，用關鍵字與意圖判斷（例如出現「幫我修」「直接改」偏向
   Engineer Mode；出現「有沒有被駭」偏向 Security Mode；出現「幫我寫」
   偏向 Content Writer Mode）。
3. 不確定時，明確詢問使用者要用哪個模式，不臆測。

## 為什麼先做 Consultant Mode

Consultant Mode 是唯一一個「純讀取、零副作用、對任何網站都能立即提供價值」
的模式，也是其他模式的資料基礎（Engineer Mode 修復的問題來自 Consultant
Mode 的 Finding；Content Writer Mode 的內容缺口分析也可以複用 Consultant
Mode 的 crawler）。因此 v0.1.0 MVP 集中火力把 Consultant Mode 做完整、
做正確，其他模式先定義好介面與 prompt，避免囫圇吞棗。
