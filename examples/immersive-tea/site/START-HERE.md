# 山嵐茶屋 網站專案

目前是離線產出的可預覽網站；未部署、未生圖、未呼叫 API。

1. 在本目錄執行 `python -m http.server 8000 --bind 127.0.0.1 --directory public`，開啟 http://localhost:8000。只公開 public，不要公開專案根目錄。
2. 將 brief.json 交給網站技能繼續引導。填入真實內容，依 asset-manifest.json 透過 GPT Image 生成並審核圖片。
3. 以 `seo-advisor website build --brief brief.json --out ./next-version` 重建到新目錄；不會覆蓋原目錄。
4. 執行 `seo-advisor website check --site .`。exit 2 表示草稿待補；exit 0 只表示離線 SEO 基線通過，仍須人工／瀏覽器驗證、交易測試及部署後檢查。

選擇的主機：cloudflare。部署前先查核當時免費額度、帳務需求、網域與費用；主機免費不等於生圖、金流、網域全都免費。
設定 wrangler.jsonc 的唯一專案名稱。Cloudflare 橘雲是 DNS 代理；此設定使用 Workers Static Assets 託管 public。確認帳號與目標後再部署。

以下只提供指令，建站工具沒有執行。先完成內容、圖片、網址與交易檢查，再確認目標帳號和發布意願。必須先安裝 Node.js LTS（Cloudflare/Firebase）或 Google Cloud CLI（GCP）。將所有 YOUR_* 代換成自己的設定。

```sh
npx wrangler login
npx wrangler whoami
npx wrangler deploy --dry-run
# 確認 wrangler.jsonc 專案名稱、帳號及費用後才執行：
npx wrangler deploy
```
[Cloudflare 官方靜態網站流程](https://developers.cloudflare.com/workers/static-assets/get-started/)

購物清單若顯示『示範』，只在瀏覽器記憶體暫存；沒有庫存、訂單、付款或後台。外部結帳是逐項商品連結，不會把示範清單轉成正式訂單。
