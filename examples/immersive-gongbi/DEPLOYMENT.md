# 公開預覽與維護

[一筆敬意：工筆媽祖畫像](https://open-seo-gongbi-demo.digimkt.workers.dev/)

2026-09-18 發布於 Cloudflare Workers Static Assets，Worker 為 `open-seo-gongbi-demo`。
目前部署版本：`bb8c57f6-ade0-4a36-8087-a515ae7b3c6f`。只發布 `public/`，沒有後端服務或付款功能。
網頁保留 noindex；四張 PNG 原圖、生成紀錄與研究文件保留在公開目錄外，
部署時只傳輸壓縮後的 WebP 圖像。

2026-09-23 已讀回 11 份公開檔案，內容雜湊全部與本機一致；不存在路徑與生成紀錄
網址單獨讀取皆回傳 404。手機首屏選用 178,322 B 的 WebP。相同 Lighthouse 手機
模擬條件下，更新前 LCP 2.11 秒、更新後 1.05 秒，兩次 LCP 元素都是主標文字。
這是實驗室診斷，不能代替真實使用者的 Core Web Vitals 或搜尋成效資料。
公開瀏覽器實測勾線、跳章、同位置倒帶、靜態閱讀；本機另測手機完整畫幅、訪客落印與對話框鍵盤操作。

從儲存庫根目錄，以有權限的 Cloudflare 帳號執行：

```bash
npx wrangler@4.134.0 deploy --dry-run --config examples/immersive-gongbi/preview.wrangler.jsonc
npx wrangler@4.134.0 deploy --config examples/immersive-gongbi/preview.wrangler.jsonc
```

複用至其他帳號時先改 Worker 名稱，再更新預覽網址；部署前檢查只上傳 `public/`。
本例以三張同構圖的工筆素材及 SVG 筆路表現作畫，並非真實畫師工作紀錄。
