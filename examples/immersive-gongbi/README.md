# 一筆敬意｜工筆媽祖畫像

**[直接體驗：一筆敬意｜工筆媽祖畫像](https://open-seo-gongbi-demo.digimkt.workers.dev/)**

免下載、免登入。點首頁的「開始作畫動畫」後往下捲動，看畫筆依序勾線、設色與敷金；
也可 [直接進入勾線動畫](https://open-seo-gongbi-demo.digimkt.workers.dev/#outline)。
往上捲動可以倒帶，最後選「安／定／願」留下訪客印；「靜態閱讀」可關閉動態。

以同一構圖的白描、淡彩與完成稿，呈現一幅工筆神像逐步成形的過程。
所有畫作與畫案素材皆由 GPT image 生成，並非畫師實作紀錄或文物作品。
此例不提供預約、委託或收款；訪客落印只作用於本頁，不是宗教儀式。

## 素材與實作

- `public/assets/final.png`：完成稿，1024×1536。
- `public/assets/linework.png`：以完成稿為參考編輯的白描階段。
- `public/assets/underpaint.png`：同構圖的淡彩階段。
- `public/assets/studio.png`：筆、墨、顏料與絹面的畫案情境。
- `generation-record.json`：完整生成／編輯提示詞及素材來源。
- `references.md`：工筆敘事與媽祖造像所依據的文化機構資料。
- `public/index.html`、`styles.css`、`site.js`：原生 HTML、CSS、SVG 遮罩與 JavaScript；不需要前端建置套件。

畫稿、勾線、分染、敷金、落印是這個互動作品的五段敘事。筆路、局部遮罩與金線細節隨
進度變化，並非單張圖片放大。關閉動態或無法執行 JavaScript 時，仍可閱讀階段圖文與完整畫作。
訪客題印只作用於此頁，沒有預約、交易或宗教效驗承諾。

## 本機預覽

在此資料夾執行：

```bash
python -m http.server 8789 --bind 127.0.0.1 --directory public
```

開啟 `http://127.0.0.1:8789/`。公開發布時只上傳 `public/`，部署設定為 `preview.wrangler.jsonc`。

公開部署與回復方式見 [部署紀錄](DEPLOYMENT.md)，操作檢查見 [驗證紀錄](VERIFICATION.md)。
