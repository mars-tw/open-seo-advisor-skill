---
name: Open SEO Advisor
slug: open-seo-advisor
version: 0.1.3
license: Apache-2.0
description: >
  蒸餾多位資深 SEO 顧問方法論與 Google 官方標準，自動偵測網站全域 SEO 問題，
  並提供顧問／工程師／資安／文章寫手／外掛開發／Meta 廣告優化／產圖素材七種
  模式，協助任何產業、任何規模的網站進行 SEO 健檢、修復、內容產出、廣告優化
  與素材製作。
triggers:
  - "/seo"
  - "/seo-audit"
  - "/seo-fix"
  - "/seo-security"
  - "/seo-write"
  - "/seo-plugin"
  - "/seo-ads"
  - "/seo-image"
  - "幫我做 SEO 健檢"
  - "分析這個網站的 SEO 問題"
  - "幫我看廣告成效"
  - "產生廣告素材"
  - "seo audit"
  - "site health check"
---

# Open SEO Advisor

開源、可攜、不綁定單一廠商 API 的全域 SEO 顧問技能。目標是讓任何人（個人站長、
代理商、企業內部團隊、開源貢獻者）都能用同一套方法論，對任何產業、任何技術棧的
網站做出資深顧問等級的 SEO 診斷、修復、內容產出與外掛開發。

## 安全前提（優先於一切功能）

1. **只處理使用者明確授權的網站、主機、原始碼與帳號**。不得對未授權的第三方網站
   進行任何超出公開頁面讀取以外的操作（不得嘗試登入、繞過驗證、探測漏洞）。
2. **預設 read-only、預設 dry-run**。任何會寫入檔案、部署、修改 DNS/CDN 設定、
   呼叫會產生副作用的 API 的操作，必須先產出「執行計畫」給使用者確認，取得
   明確同意後才可執行。
3. **絕不將憑證、金鑰、token、cookie、`.env` 內容寫入報告或程式碼**。憑證只能
   來自環境變數、OS keychain、使用者當下輸入，且只在記憶體中使用。
4. **最小權限原則**：能用 read-only API 就不用有寫入權限的帳號；能用一次性
   command 就不要求持久 shell 存取。
5. 對正式環境（production）的任何寫入或部署操作，一律要求人工二次確認。

## 七大模式總覽

| 模式 | 觸發 | 目標 | 詳細規格 |
|---|---|---|---|
| 顧問模式 Consultant | `seo-advisor audit consultant` | 全站健檢、產出診斷報告與優先順序 | `docs/modes.md#consultant-mode` |
| 工程師模式 Engineer | `/seo-fix engineer` | 直接修復技術 SEO 問題（sitemap/canonical/hreflang/schema/CWV） | `docs/modes.md#engineer-mode` |
| 資安模式 Security | `/seo-security` | 檢查與 SEO 相關的資安風險 | `docs/modes.md#security-mode` |
| 文章寫手模式 Content Writer | `seo-advisor write` | 依 SEO 權威指導原則產出內容 | `docs/content_writer_guide.md` |
| 外掛開發模式 Plugin Dev | `/seo-plugin` | 開發 WordPress 等 CMS 的 SEO 外掛 | `docs/modes.md#plugin-dev-mode` |
| Meta 廣告優化 Meta Ads | `seo-advisor ads` | 診斷 Meta 廣告帳戶、產出優化建議與 dry-run 行動計畫 | `docs/meta_ads_mode.md` |
| 產圖素材 Image Material | `seo-advisor image` | 為廣告/社群/文章產生圖像素材（provider 抽象層） | `docs/image_material_mode.md` |

模式路由邏輯見 `scripts/seo_advisor/router.py`：使用者可用明確指令指定模式，
也可以用自然語言描述需求，由 router 判斷最適合的模式；不確定時一律用
`AskUserQuestion` 式的澄清詢問，不要自行臆測。

## 目前實作狀態（v0.1.3）

- ✅ 顧問模式（Consultant Mode）：HTTP/LocalArchive connector、
  技術面 crawler、Finding/Report schema、Markdown+JSON 報告產出、
  noindex 檢查、非 UTF-8 編碼偵測、category-weighted 健康分數。
  詳見 `docs/architecture.md` 與 `docs/modes.md`。
- ✅ 文章寫手模式（Content Writer Mode）：`LLMProvider` 抽象層
  （Anthropic / OpenAI / Local / Mock）、brief → outline → draft → QA
  四階段流程、`seo-advisor write` 指令。詳見 `docs/content_writer_guide.md`。
- ✅ Meta 廣告優化模式（Meta Ads Mode）：`AdsProvider` 抽象層
  （Meta / Mock）、`AdsSafetyPolicy` 多重預算防護、廣告成效診斷、
  dry-run 行動計畫、`seo-advisor ads audit/plan/demo`。實際代操（動用
  真實預算）預設全鎖，詳見 `docs/meta_ads_mode.md`。
- ✅ 產圖素材模式（Image Material Mode）：`ImageProvider` 抽象層
  （OpenAI / Mock）、合規前置檢查、多變體生成、與 Content Writer 串接、
  `seo-advisor image generate/demo/from-content`。詳見 `docs/image_material_mode.md`。
- ✅ 新手體驗：互動精靈（`seo-advisor` / `seo-advisor start`）、
  URL 自動正規化、人話錯誤訊息、白話文報告（`report-beginner.md`）、
  Demo 模式（`seo-advisor demo`）、一鍵安裝腳本、`QUICKSTART.md`。
- ✅ 資安強化：Connector 層 `SafetyPolicy`（dry-run/capabilities/SSRF
  防護程式化約束）、zip slip 防護、robots.txt 遵循與 rate limit、
  sitemap 爬取範圍限制。詳見 `docs/connector_contract.md`。
- 🚧 工程師／資安／外掛開發模式：介面與 prompt 模板已定義於
  `prompts/`，執行邏輯將於後續版本（v0.2.0 起）逐步實作，
  詳見 `docs/roadmap.md`。

## 快速開始

**完全不會寫程式？** 執行 `install.ps1`（Windows）或 `install.sh`
（Mac/Linux），再執行 `seo-advisor`，會有問答式精靈引導你完成第一次
掃描。詳見專案根目錄的 `QUICKSTART.md`。

進階指令：

```bash
cd scripts
pip install -e .
seo-advisor audit consultant --url example.com --out ./report
```

或使用本地原始碼包：

```bash
seo-advisor audit consultant --source ./my-website --out ./report
```

不確定怎麼用？直接執行 `seo-advisor demo` 可以先看一份範例報告，
不需要輸入任何網址。

## 目錄導覽

- `docs/architecture.md`：整體架構、Connector 抽象層、資料模型。
- `docs/modes.md`：五大模式的完整檢查清單、輸出格式、外部資料來源。
- `docs/connector_contract.md`：WebsiteConnector 介面規格與資安要求。
- `docs/content_writer_guide.md`：SEO 寫作品質規範與 prompt 模板。
- `docs/i18n_seo_guide.md`：跨產業與國際化 SEO 檢查重點。
- `docs/roadmap.md`：MVP 到 1.0 的實作路線圖。
- `schemas/`：Finding／Report／Connector 的 JSON Schema。
- `config/`：預設檢核規則、評分權重、產業與地區設定檔。
- `prompts/`：各模式的 system prompt 模板。
- `scripts/seo_advisor/`：Python 實作本體。

## 貢獻與授權

本專案採 **Apache-2.0** 授權，開源給全球任何人使用、修改與再散布，詳見
`LICENSE` 與 `CONTRIBUTING.md`。歡迎針對不同產業、語言、CMS 或雲端平台
貢獻新的 connector、analyzer、fixer 或產業設定檔。
