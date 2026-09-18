# 公開預覽

固定網址：[一片葉的回家路](https://open-seo-advisor-demo.digimkt.workers.dev/)。
公開日期：2026-09-18。使用 Cloudflare Workers Static Assets，Worker 名稱為
`open-seo-advisor-demo`；部署設定是本目錄的 `preview.wrangler.jsonc`。

只發布 `site/public/` 的 HTML、CSS、JavaScript 與圖片，沒有資料庫、支付、API 金鑰或
後端收款服務。保留 noindex，網站明示虛構品牌與示範性質。
已驗證 HTTPS、13 份公開資源內容、故事操作，以及不存在路徑和非公開 `brief.json` 的 404。

維護者從儲存庫根目錄，使用自己有權限的 Cloudflare 帳號執行：

```bash
npx wrangler@4.134.0 deploy --dry-run --config examples/immersive-tea/preview.wrangler.jsonc
npx wrangler@4.134.0 deploy --config examples/immersive-tea/preview.wrangler.jsonc
```

第一次複用範例到別人的帳號時，應改 Worker 名稱並更新文件網址。不要將整個技能儲存庫
當作網站目錄。部署後確認頁面、圖片、章節導覽、點燈與靜態閱讀正常，再更新文件入口。
Cloudflare 保留部署版本；需要回復時使用已核對的前一版版本 ID，僅操作這個示範 Worker。
