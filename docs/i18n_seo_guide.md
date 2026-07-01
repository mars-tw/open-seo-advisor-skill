# 跨產業與國際化 SEO 檢查重點

## 產業差異化檢查重點

對應 `config/industry_profiles.yaml` 中定義的 profile，Consultant Mode
在 `--industry` 參數指定後會套用額外檢查項目與 impact 權重調整。

| 產業 | 業務型態 | 額外檢查重點 |
|---|---|---|
| 電子商務 | B2C | Product/Offer/AggregateRating schema、價格與庫存準確性、faceted navigation 的 canonical 處理、分頁策略、分類頁內部連結、缺貨頁處理、評論 schema |
| SaaS | B2B/B2C | Feature 頁完整性、比較頁存在性、整合頁 SEO、文件（docs）可索引性、資安合規頁面、Demo CTA 清晰度 |
| 在地服務業 | B2C | NAP（Name/Address/Phone）一致性、LocalBusiness schema、服務區域頁、Google Business Profile 對應、評論策略、地圖嵌入 |
| 內容媒體 | B2C | 作者頁與專業背景、發布/更新日期策略、主題群集（topic cluster）結構、news/video sitemap、廣告體驗與 CWV 衝突、付費牆 schema |
| 企業官網 | B2B | Organization schema、案例研究/白皮書存在性、解決方案/使用情境頁、領導團隊與關於我們頁、多地區辦公室頁、轉換路徑清晰度 |

新增產業 profile 時，請直接編輯 `config/industry_profiles.yaml`，
並在 PR 中說明依據的產業慣例來源。

## 國際化 SEO 檢查重點

### hreflang 規則（對應 `config/locale_profiles.yaml`）

- **雙向對應**：每個語言/地區版本都必須在自己的 hreflang 標記中列出
  自己與所有其他對應版本，缺一不可。
- **`x-default`**：建議用於語言/地區選擇頁或作為 fallback 版本。
- **語言碼標準**：使用 ISO 639-1（如 `en`、`zh`、`ja`），地區碼用
  ISO 3166-1 alpha-2（如 `US`、`TW`、`JP`），組合為 `en-US`、`zh-TW`。
- **三種宣告形式擇一貫徹**：HTML `<head>` 標記、HTTP header、或 XML
  sitemap，同一網站不應混用造成衝突。
- **canonical 與 hreflang 不可矛盾**：canonical 指向的版本必須與
  hreflang 宣告的自我參照一致。
- **URL 需為完整絕對路徑**：不可使用相對路徑。

### 在地化內容（不只是翻譯）

- 價格需顯示當地貨幣與稅制（依 `locale_profiles.yaml` 的 `currency`）。
- 日期格式需符合當地慣例（見 `date_format` 欄位）。
- 案例、客服資訊、法規遵循聲明需符合當地實際情況，不得沿用其他市場的
  內容直接翻譯。
- 需考慮當地主要搜尋引擎差異：例如中國大陸市場需額外考慮百度 SEO
  邏輯與 ICP 備案；韓國市場 Naver 生態系影響力大於 Google；
  日本市場 Yahoo! Japan 雖採用 Google 演算法，但在地內容習慣仍需獨立
  審視。

### Local SEO 檢查重點

- Google Business Profile 資料與網站 NAP 資訊一致。
- `LocalBusiness` 結構化資料完整（營業時間、服務區域、評論）。
- 多地點/多分店網站需有獨立且不重複的地區 landing page，避免地區頁
  之間內容高度相似造成自我競爭（keyword cannibalization）。
- 在地評論策略與在地連結建立（local citations）。

## B2B vs B2C 差異

- **B2B**：決策鏈長、決策者非單一人，內容重點在建立專業信任
  （case study、白皮書、產業洞察），轉換路徑通常是「詢問/預約 demo」
  而非直接購買，SEO 檢查應重視 solution page 與 use case page 的
  搜尋意圖對齊。
- **B2C**：決策週期短，內容重點在產品/服務頁的清晰度、價格透明度、
  使用者評論與信任訊號、行動裝置體驗與頁面速度（直接影響轉換率）。
