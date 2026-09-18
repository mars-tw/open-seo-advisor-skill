# 引導式建站

這份文件給執行技能的 agent 使用。先推進網站，不要把整份規格丟給新手。

## 先選訪客要完成的事

| 站型 | 訪客目的 | 預設頁面 |
|---|---|---|
| 銷售站 `sales` | 詢問、預約、購買方案 | 首頁／方案／可信證據／FAQ／聯絡及政策 |
| 購物站 `shop` | 找商品、確認規格、結帳 | 敘事首頁／分類／商品獨立 URL／購物車／結帳／配送退換貨與隱私 |
| 體驗站 `experience` | 完成互動並帶走結果 | 敘事／體驗／結果與重玩／玩法／關於與 FAQ |

類型可以混合。塔羅商城可用故事入口＋抽牌＋商品目錄，先決定主要目的。
不要要求購物者看完整故事才能購買。已提供的品牌、參考與主機不重問；每輪最多三題。
「免費」要問清能否接受 billing 與超額費用；不能把免費額度說成保證零帳單。

`site-plan.md` 保留站型、受眾、CTA、頁面 URL→搜尋意圖→內容→CTA、事實來源、
視覺方向、素材狀態、商務模式、主機與查核日期、已有授權、進度與待補資訊。
內部文件、原始素材備份及憑證不放進公開 `public/`／`dist/`。

## 架構與實作

- 有專案就先讀 AGENTS.md、套件、路由、資料與部署設定並沿用技術棧，不強制換框架。
- 新內容／銷售站可用靜態 HTML 或 Astro 等預渲染架構；React／Vue 可供局部互動，
  核心內容與商品資訊仍需完整 HTML 回應。商務後端依功能加入。
- 視覺先決定品牌專屬主張，再挑動效。複雜時間軸才加動畫函式庫，查當時官方文件與授權。
- 指定 Sites 時遵守 Sites 工作流；指定 Cloudflare／Google 時提供可攜原始碼與輸出，
  不暗中改綁其他平台。

## CLI：離線起始點

```bash
python -m pip install -e ./scripts
seo-advisor website init --out ./my-site
seo-advisor website demo --type shop --hosting cloudflare --out ./shop-demo
seo-advisor website build --brief ./brief.json --out ./my-site-v2
seo-advisor website check --site ./my-site-v2
python -m http.server 8080 --bind 127.0.0.1 --directory ./my-site-v2/public
```

瀏覽器開啟 `http://127.0.0.1:8080`。`init` 問品牌、站型、主機與可留白的正式網域，
產出新目錄；`demo` 不連網、不收費；`build` 不覆寫既有目錄。

輸出含 `public/`、`brief.json`、`asset-manifest.json`、`site-report.json` 與部署設定。
brief 範例在 `scripts/seo_advisor/website/templates/brief.example.json`。
`check` exit 0＝`baseline_ready`、2＝`scaffold`（待補）、1＝`invalid`。

目前 CLI starter 的介面語言為 `zh-TW`；其他語言須由 agent 客製化文字與 metadata，
不能只改 lang 就宣稱已翻譯。CLI 網址驗證只查語法，不查 DNS、可連線性或收款端功能。

**CLI 不呼叫 GPT、不產圖、不自動發布，也不實作商店後端。** Agent 依 [素材流程](website-assets.md)
接入真正圖文，再客製設計、多頁與功能。不可把 demo 佔位圖說成 GPT 圖片，也不可把
單頁骨架當完成的多頁商店。使用者只要模板時才在骨架範圍交付。

## 從骨架到成品

需要敘事動畫時，在 brief 加上 `story_scenes`，直接參考
[完整四幕輸入](../examples/immersive-tea/brief.json) 與 [故事分鏡](../examples/immersive-tea/storyboard.md)：

| 欄位 | 用途 |
|---|---|
| `story_scenes` | CLI 支援 2–8 幕，與 `chapters` 一對一；每幕有 `image`、`effect`、`actor_pose`、`image_position` 與可選 `effect_points` |
| `story_actor` | 跨幕共用主角的本機圖片；建議真正透明 PNG，保留獨立圖層 |
| `story_start_pose` | 主角在第一幕的出發位置；各幕 `actor_pose` 是該幕的抵達位置 |
| `story_action` | 可選互動的按鈕、提示、操作後及未操作的結尾文案 |

座標以各幕原圖的百分比表示，顯示時按 cover／`image_position` 換算。效果可選
`mist`／`wind`／`lanterns`／`steam`／`none`；根據分鏡選擇，不能為每個產業硬套茶山情節。
這些是可攜起始引擎的欄位，不限制 agent 為專案實作更多場景、物件狀態或互動。

1. 依品牌重寫內容、建立頁面與內部連結，保留事實來源；不沿用示範茶屋的虛構設定。
2. 依各幕規劃圖片、前景、文字與互動。CLI 單張 hero 可擴充為多幕圖片與前景層，
   圖片先能顯示，再加入動態。
3. 按 [商務流程](website-commerce.md) 做真功能；超出 CLI 的功能仍要由 agent 繼續實作。
4. [驗收](website-quality.md) 後依 [託管指南](website-hosting.md) 引導帳號、方案、預覽、
   正式域名與回滾。已有授權足夠便續行。

## 使用者提供的參考

2026-09-18 瀏覽器實際觀察：

- [星芽快遞](https://starbud-courier.dumb-money-crypto-bu.chatgpt.site/)：全幅紙藝場景、
  五幕導覽、聲音／減少動態開關、跳過故事，後面接遊戲與角色／關卡內容。
- [月相塔羅](https://taiwan-tarot-store.taiwan-tarot-store.workers.dev/)：森林 hero、前景牌卡、
  四幕故事、月蛾與門的操作提示，結尾接反思卡與商店導覽。當時首頁明示價格、庫存、配送
  待商店準備完成，因此不能推定它已能真實收款。

借鑑敘事進程、視覺層次、可略過與明確目的，不複製品牌、角色、圖片或整站程式。
未來網站不必都是奇幻、茶、塔羅或深色；每個品牌重新決定設計。
