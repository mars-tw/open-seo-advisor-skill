# Changelog

本專案採用 [Semantic Versioning](https://semver.org/)。

## [0.1.1] - Unreleased

### Added（新手體驗優化）

- `QUICKSTART.md`：5 分鐘上手指南，不要求先懂 Python 或 SEO。
- `install.ps1` / `install.sh`：一鍵安裝腳本，自動偵測 Python、建立
  虛擬環境、安裝套件並驗證安裝結果。
- `docs/install-troubleshooting.md`：常見安裝問題排解。
- `docs/glossary-for-beginners.md`：SEO 術語白話對照表（sitemap、
  canonical、robots.txt 等，用生活化比喻解釋）。
- CLI 互動精靈（`seo-advisor` / `seo-advisor start`）：不帶參數執行時
  用問答方式引導完成掃描，不需要記任何指令參數。
- `seo-advisor demo`：不需要輸入任何網址，直接用內建範例資料產生
  完整報告，方便新手在掃描自己的網站前先了解報告長相。
- URL 自動正規化（`url_utils.py`）：使用者輸入 `example.com` 會自動補上
  `https://`，不再要求手動輸入完整網址格式。
- 人話錯誤訊息（`errors.py`）：連線逾時、網址錯誤、檔案不存在等常見
  錯誤，預設顯示可理解的說明與下一步建議，而非 Python traceback；
  加上 `--debug` 才顯示完整技術細節。
- 白話文報告層（`beginner_report.py` → `report-beginner.md`）：用「房屋
  健檢」比喻解釋網站健康分數與 P0-P3 優先順序，附上「最該先處理的
  3 件事」，供非技術人員（老闆、客戶）閱讀。
- CLI 進度提示：掃描過程顯示「第 X/4 步」階段性文字，讓使用者知道
  工具正在運作而非卡住。
- 報告輸出改為固定檔名（`report-beginner.md` / `report.md` /
  `report.json`），不再使用隨機 ID 檔名，方便新手直接找到檔案。
- 修正孤兒頁（orphan page）誤判：單頁網站的唯一頁面不再被誤判為孤兒頁。

## [0.1.0] - Unreleased

### Added

- 專案骨架、SKILL.md、文件（architecture / modes / connector contract /
  content writer guide / i18n guide / roadmap）。
- Finding / Report / Connector 的 JSON Schema。
- `WebsiteConnector` 抽象介面，實作 `HTTPConnector`、`LocalArchiveConnector`。
- 顧問模式（Consultant Mode）核心：技術面 crawler（robots.txt / sitemap /
  canonical / title・meta・H1 / 內外連結 / 狀態碼）、scoring、
  Markdown + JSON 報告產出。
- CLI 入口（`seo_advisor.cli`）與五大模式路由骨架（工程師／資安／文章寫手／
  外掛開發模式先提供 prompt 模板與介面，執行邏輯留待後續版本）。
- 基本測試與範例設定。

### 尚未實作（規劃於後續版本，見 `docs/roadmap.md`）

- Engineer Mode 的自動修復（fixers）。
- Security Mode 的主動掃描邏輯。
- Content Writer Mode 的 LLM 呼叫整合。
- Plugin Dev Mode 的 WordPress 外掛 scaffold。
- SSH / Git / WordPress API / Cloudflare / cPanel connector。
