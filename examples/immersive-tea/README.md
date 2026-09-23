# 山嵐茶屋：《一片葉的回家路》

陪一片迷路的茶葉穿過晨霧、越過吊橋，將溫暖送回山中茶屋。
四幕有不同場景，茶葉是獨立透明圖層；訪客的點燈操作會改變後續燈火及結尾。
山嵐茶屋為虛構品牌，此例不提供預約或收款。

**[直接體驗：一片葉的回家路](https://open-seo-advisor-demo.digimkt.workers.dev/)**

免下載、免登入。進入故事後往下捲動、點亮茶葉，再倒回吊橋，最後回到茶杯終幕。
章節導覽可以直接跳轉；重玩會重設選擇；關閉動態後四幕改為正常圖文閱讀。
也可 [直接進入第一幕](https://open-seo-advisor-demo.digimkt.workers.dev/#story)。

維護與重新發布方式見 [部署說明](DEPLOYMENT.md)。

## 本機預覽

在這個資料夾執行：

```bash
python -m http.server 8787 --bind 127.0.0.1 --directory site/public
```

開啟 `http://127.0.0.1:8787`，即可在本機查看同一份故事。
預覽保留 noindex，未連接正式商品或支付帳號。

這個網站有[獨立的製作說明頁](site/public/about/index.html)，可從首頁導覽與頁尾進入。
兩頁有各自的 title、description 和 H1，故事章節以 H2／H3 整理。它們都設為
`noindex`，所以不能拿來證明自然搜尋曝光、排名或 AI 回答引用；要評估正式品牌的 SEO，
還須以實際搜尋需求、可收錄頁面和上線後資料驗證。

## 素材與原始碼

- `storyboard.md`：敘事因果、每幕動作與畫面驗收。
- `brief.json`：四幕、原圖座標、主角、操作及結尾的可編輯契約。
- `assets/scene-01-mist.png` 至 `scene-04-cup.png`：GPT image 生成的四幕場景。
- `assets/actor-tea-leaf.png`：GPT image 生成的透明主角，已檢查 alpha。
- `story-generation-record.json`：此次五張圖的生成 prompt 與來源。
- `generation-record.json`／`assets/tea-mountains.png`：最初視覺方向的來源紀錄。
- `experience.css`：本範例 hero 的全幅視覺，並非所有品牌的固定風格。
- `site/`：預覽輸出；只有 `public/` 是網站公開目錄。
- `site/public/assets/*.webp`：從 GPT PNG 原圖壓縮的傳輸版本；首屏提供 960px
  變體。原始 PNG 保留在 `assets/`，不放進網站公開目錄；`optimize_assets.py`
  可在更新原圖後重建，需安裝 Pillow。

2026-09-23 本機檢查：首頁首屏原圖 2,014,904 bytes，完整 WebP 170,016 bytes，
960px WebP 78,554 bytes。公開站在此修改部署前的模擬手機 Lighthouse LCP 為 11.0 秒；
圖片縮小只是修正傳輸瓶頸，新的 LCP 必須在更新後重新量測，不能預先宣稱達標。

## 重新建置

重新建立到新目錄：

```bash
seo-advisor website build --brief brief.json --out ./site-v2
```

四幕故事由生成器直接產出。要保留本例 hero 的全幅樣式，複製 `experience.css` 到
新站 `public/`，在 `styles.css` 後加入 `<link rel="stylesheet" href="experience.css">`。
銷售與購物入口可用 `website demo --type sales`／`website demo --type shop`；實際品牌
仍應重新規劃故事、頁面、商品事實及商務功能。
