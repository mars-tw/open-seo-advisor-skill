# 沉浸式網站的 SEO／AEO 實作

官方文件查核日期：2026-09-18。這裡的 AEO 指讓使用者與搜尋／回答系統更容易理解、查證網站內容；不保證排名、收錄、精選摘要或 AI 引用。

## 先決定每頁要回答什麼

沿用專案已確認的品牌、客群、商品與事實，只補問會改變架構的缺口。先做意圖與頁面對照，再畫滾動分鏡。

| 使用者的問題 | 建議內容 | 適合的頁面 |
| --- | --- | --- |
| 這是什麼、適合誰？ | 具體介紹、限制、真實情境、主要行動 | 首頁／銷售頁 |
| 跟其他方案差在哪？ | 可查證的規格、費用、比較條件 | 比較／選購指南 |
| 有哪些款式、怎麼買？ | 分類、商品規格、價格、庫存與履約資訊 | 商品分類／個別商品頁 |
| 怎麼體驗、結果代表什麼？ | 操作說明、可讀文字、結果限制 | 體驗入口／說明頁 |
| 誰負責、遇到問題找誰？ | 品牌資訊、聯絡、服務與交易政策 | 關於／聯絡／政策頁 |

每頁記錄 URL、主要意圖、標題、h1、摘要、內部連結、主要行動、依據與維護責任。不要為每個近義關鍵字複製一頁。GPT 可寫初稿，經營者仍須核實價格、規格、資格與案例；沒有證據的評價、得獎、療效或銷量不生成為事實。

## 讓動畫建立在可讀內容上

本技能預設使用 SSG／SSR 或直接輸出 HTML。動畫是漸進增強：瀏覽器尚未執行 JavaScript 時，仍有標題、主要介紹、商品內容、連結與 CTA。這是降低渲染與可及性風險的實作選擇；Google 能處理 JavaScript，但渲染仍有條件與限制。[JavaScript SEO 基礎](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics)

- 主文保留在 DOM；不把品牌名、商品描述、價格或答案只畫在 canvas、WebGL、影片與生成圖片中。
- 使用真實 `<a href>` 連結。重要商品／服務要有可直接開啟、重新整理與分享的 URL；章節錨點可輔助長頁導覽，不代替商品頁。
- 滾動揭露內容時，避免必須拖曳、點擊或捲到指定位置才向伺服器要求主要文案。
- 預設內容可見，確認動畫程式可用後再增強；支援 `prefers-reduced-motion`、鍵盤與手機觸控。停止動畫時仍保留完整閱讀及購買路徑。
- 正文與 CTA 用 HTML 疊在 GPT 圖像上，重要字詞可選取、可翻譯。裝飾圖用空 `alt`，內容圖描述實際畫面，不塞關鍵字。
- 為圖片設尺寸；首屏主要圖優先載入，下方圖延遲載入。避免整頁圖片序列同時下載；以實際手機檢查讀取與互動。

## 每頁的技術契約

| 項目 | 實作與驗證 |
| --- | --- |
| HTTP | 正常頁 200；搬家 301／308；不存在的內容真實 404，不能一律回首頁 200 |
| 標題與摘要 | 描述本頁實際用途；各頁避免相同預設標題，主要 h1 清楚且與可見內容一致 |
| canonical | 使用最終 HTTPS 網址；預覽網域、參數頁與正式站處理一致，不把所有商品 canonical 到首頁 |
| 收錄控制 | 正式可收錄頁無意外 `noindex`；CDN、WAF、登入及 robots 不阻擋需要的 HTML、CSS、JS 與圖片 |
| sitemap | 列出想收錄的 canonical URL；排除購物車、結帳、登入、搜尋結果與敏感個人資料；`lastmod` 使用實際重要修改日期 |
| 社群分享 | title、description、絕對網址的預覽圖、頁面 URL 可讀回；這是分享呈現，不保證搜尋排名 |
| 內部連結 | 從首頁／分類可走到重要頁，連結文字說明目的，不只寫「點這裡」 |
| 多語 | 有真實翻譯才建語言頁與對應關係；不生成大量空白地區頁 |

robots.txt 控制爬取；要讓爬蟲讀到 `noindex`，該頁不能同時被 robots 阻擋。[noindex 指引](https://developers.google.com/search/docs/crawling-indexing/block-indexing) 私人頁面須用登入與授權保護，不能靠 robots 保密。Sitemap 是發現提示，提交不保證收錄。[Sitemap 指引](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)

## AEO 內容與結構化資料

用自然的問題標題、直接回答、條件、步驟、比較表、資料日期及原始來源，幫讀者快速理解。答案寫多長取決於問題，不設「必須 40–60 字」或特定分塊法。Google 官方沒有要求為 AI Search 特製寫法或 schema；`llms.txt` 可供其他有支援的系統使用，Google 明確說不採用它作為排名／可見度因素。[Google AI 最佳化指引](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)

採 JSON-LD 時只描述本頁實際存在、使用者可見且可證實的內容：[結構化資料政策](https://developers.google.com/search/docs/appearance/structured-data/sd-policies)

| 類型 | 使用條件 |
| --- | --- |
| `Organization`／`LocalBusiness` | 真實品牌／營業地點；不編造地址、分店或證照 |
| `BreadcrumbList` | 對應可理解的實際頁面層級 |
| `Product`／`Offer` | 個別真實商品；名稱、幣別、價格、供貨與頁面／商家後端一致 |
| `Article` | 有實際作者、日期與編輯內容，適合指南／文章 |
| `FAQPage` | 可選語意標記，問題與回答須可見；本技能不以它作為 Google rich result 驗收條件 |

商品頁按[Product 文件](https://developers.google.com/search/docs/appearance/structured-data/product-snippet)檢查必要欄位；未有真實評價時，省略 `review`／`aggregateRating`。不要為了通過檢測虛構星等、促銷截止日或庫存。

**查核更新：Google 自 2026-05-07 起停止呈現 FAQ rich results，並於 2026 年 6 月移除該功能文件。** FAQ 仍可作為有用的頁面內容；舊版「加 FAQ schema 就有搜尋問答展開」或「只限政府／健康站」說法不可沿用。[Google 官方更新](https://developers.google.com/search/updates)

Google AI 搜尋呈現以可爬取、已收錄、可顯示摘要的內容為基礎；符合文件也不保證收錄或被引用。[AI Features 技術說明](https://developers.google.com/search/docs/appearance/ai-features) 部署後也檢查 Search Console 當時提供的 generative AI 收錄／排除控制，依經營者意圖設定；各回答引擎的控制方式分別查核，不把 Google 規則套成全部 AI 平台的規則。

## 上線前與上線後怎麼驗收

上線前完成可確定的檢查：

1. 檢視建置後原始 HTML，確認主要內容與連結存在；停用 JavaScript、減少動態效果各測一次。
2. 抽查首頁、商品頁、文章頁、404，核對 HTTP、canonical、title、h1、可見答案與 JSON-LD。
3. 確認 robots 與 sitemap 使用正式網域；測試搜尋引擎需要的資源可公開存取。
4. 用手機與桌面檢查遮擋、橫向溢出、字級、焦點、動態效果與圖片失敗情況；確認主要 CTA 在不同顯示模式仍可用。
5. 用 Rich Results Test／Schema 驗證工具檢查適用標記。語法通過與搜尋呈現資格分開記錄，工具不支援的 schema 不自動算錯誤。

上線後在授權範圍內建立 Search Console 驗證、提交 sitemap、檢查 URL 渲染與收錄。量測實際曝光、點擊、到站行為、有效詢問或交易，不把本機 Lighthouse 分數、schema 通過率換成「SEO／AEO 已成功」。若檢查某回答引擎引用情形，記錄引擎、日期、題目、語言／地區與引用 URL，標為觀察樣本。

交付報告分別寫清楚：`已實作`、`已測試`、`尚待搜尋引擎處理`、`無法驗證`。搜尋收錄與 AI 引用需要後續觀察；不可冒稱已達成。
