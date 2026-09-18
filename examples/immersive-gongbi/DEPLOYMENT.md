# 公開預覽與維護

[一筆敬意：工筆媽祖畫像](https://open-seo-gongbi-demo.digimkt.workers.dev/)

2026-09-18 發布於 Cloudflare Workers Static Assets，Worker 為 `open-seo-gongbi-demo`。
部署版本：`9d718a62-2717-4a3c-b421-b059858f32b8`。只發布 `public/`，沒有後端服務或付款功能。
網頁保留 noindex；四張圖像的生成紀錄與研究文件保留在原始碼，沒有當作公開網站檔案上傳。

已讀回 9 份公開檔案，內容雜湊全部與本機一致；不存在路徑與生成紀錄網址皆回傳 404。
公開瀏覽器實測勾線、跳章、同位置倒帶、靜態閱讀；本機另測手機完整畫幅、訪客落印與對話框鍵盤操作。

從儲存庫根目錄，以有權限的 Cloudflare 帳號執行：

```bash
npx wrangler@4.134.0 deploy --dry-run --config examples/immersive-gongbi/preview.wrangler.jsonc
npx wrangler@4.134.0 deploy --config examples/immersive-gongbi/preview.wrangler.jsonc
```

複用至其他帳號時先改 Worker 名稱，再更新預覽網址；部署前檢查只上傳 `public/`。
本例以三張同構圖的工筆素材及 SVG 筆路表現作畫，並非真實畫師工作紀錄。
