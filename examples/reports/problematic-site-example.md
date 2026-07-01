# SEO 健檢報告：C:\Users\digimkt\Desktop\SEO技能\open-seo-advisor-skill\scripts\tests\fixtures\bad_site

- 報告 ID：`seo-report-6e4281f2`
- 產生時間：2026-07-01T06:47:12.559350+00:00
- 模式：consultant
- 來源類型：local_archive

## Executive Summary

C:\Users\digimkt\Desktop\SEO技能\open-seo-advisor-skill\scripts\tests\fixtures\bad_site 的整體 SEO 健康分數為 72.5/100。 另有 2 個高影響（P1）問題建議優先排入近期排程。 本次共產出 6 項發現，詳見下方分級清單。

## Site Health Score

**72.5 / 100**

## Top Findings

- **[P1] 1 個頁面有多個 canonical 標籤** (impact=4, effort=2, confidence=1.00) — `SEO-CANONICAL_CONFLICT-001`
- **[P1] 1 個頁面缺少 <title> 標籤** (impact=4, effort=2, confidence=0.90) — `SEO-TITLE_MISSING-001`
- **[P2] 1 個頁面缺少 <h1> 標籤** (impact=3, effort=2, confidence=0.90) — `SEO-H1_MISSING-001`
- **[P2] 網站沒有 sitemap.xml** (impact=3, effort=2, confidence=0.80) — `SEO-SITEMAP_MISSING-001`
- **[P3] 網站沒有 robots.txt** (impact=2, effort=1, confidence=0.80) — `SEO-ROBOTS_MISSING-001`
- **[P3] 1 個頁面缺少 meta description** (impact=2, effort=2, confidence=0.90) — `SEO-META_DESCRIPTION_MISSING-001`

## 完整發現清單（依優先順序分組）

### P0（0 項）

（無）

### P1（2 項）

#### 1 個頁面有多個 canonical 標籤 `SEO-CANONICAL_CONFLICT-001`

- 分類：indexability
- Impact: 4 / Effort: 2 / Confidence: 1.00
- 受影響 URL：/index.html
- 建議：每個頁面只能有一個 canonical 標籤，多重宣告會讓搜尋引擎自行選擇甚至忽略，需修正模板邏輯只輸出單一 canonical。
- 驗證方式：重新爬取確認每頁僅有一個 canonical 標籤
- 建議負責模式：engineer

#### 1 個頁面缺少 <title> 標籤 `SEO-TITLE_MISSING-001`

- 分類：content_quality
- Impact: 4 / Effort: 2 / Confidence: 0.90
- 受影響 URL：/index.html
- 建議：為每個頁面撰寫獨特且能反映頁面內容的 <title>，長度建議在50-60 字元之間。
- 驗證方式：重新爬取確認問題已修正
- 建議負責模式：engineer

### P2（2 項）

#### 1 個頁面缺少 <h1> 標籤 `SEO-H1_MISSING-001`

- 分類：content_quality
- Impact: 3 / Effort: 2 / Confidence: 0.90
- 受影響 URL：/index.html
- 建議：為每個頁面加上單一、能反映頁面主題的 <h1> 標籤。
- 驗證方式：重新爬取確認問題已修正
- 建議負責模式：engineer

#### 網站沒有 sitemap.xml `SEO-SITEMAP_MISSING-001`

- 分類：indexability
- Impact: 3 / Effort: 2 / Confidence: 0.80
- 受影響 URL：/sitemap.xml
- 建議：建立 sitemap.xml 並列出所有應被索引的正規 URL，協助搜尋引擎更完整地發現與索引網站內容。
- 驗證方式：確認 /sitemap.xml 回傳 200 且為合法 XML
- 建議負責模式：engineer

### P3（2 項）

#### 網站沒有 robots.txt `SEO-ROBOTS_MISSING-001`

- 分類：indexability
- Impact: 2 / Effort: 1 / Confidence: 0.80
- 受影響 URL：/robots.txt
- 建議：建立 robots.txt 並宣告 sitemap 位置，即使目前沒有需要阻擋的路徑，也建議明確宣告以避免爬蟲行為的不確定性。
- 驗證方式：確認 /robots.txt 回傳 200 且格式正確
- 建議負責模式：engineer

#### 1 個頁面缺少 meta description `SEO-META_DESCRIPTION_MISSING-001`

- 分類：content_quality
- Impact: 2 / Effort: 2 / Confidence: 0.90
- 受影響 URL：/index.html
- 建議：為重要頁面撰寫獨特的 meta description，雖非直接排名因子，但影響搜尋結果的點擊率（CTR）。
- 驗證方式：重新爬取確認問題已修正
- 建議負責模式：engineer

## 檢查範圍說明

- Core Web Vitals、JavaScript 渲染差異比對、結構化資料驗證、Search Console/GA4 資料整合尚未實作（見 docs/roadmap.md v0.2.0）。

## 掃描統計

- urls_crawled: 1
- urls_skipped: 0
- detected_stack: static
