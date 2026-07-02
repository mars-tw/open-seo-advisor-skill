# 3 分鐘上手：一個指令搞定

這份指南寫給完全沒有寫過程式、沒有行銷/SEO 背景的人。跟著做，幾分鐘內就能拿到
一份看得懂的優化報告。

## 你不需要先懂這些

- 不需要懂 Python
- 不需要懂 SEO / 廣告 / 行銷術語
- 不需要懂命令列（Terminal / 終端機）指令
- 不需要有自己的網站（可以先用範例資料試玩）
- 不需要任何 API 金鑰、不會花任何錢

只需要：一台電腦、幾分鐘時間。

---

## 第 1 步：安裝

### Windows

1. 先確認電腦有沒有裝 Python：到「開始」選單搜尋 `PowerShell`，打開後輸入：

   ```powershell
   python --version
   ```

   - 如果看到 `Python 3.10` 或更新的版本號，代表已經裝好了，跳到步驟 2。
   - 如果出現錯誤或版本太舊，先到 <https://www.python.org/downloads/> 下載安裝最新版
     （安裝時記得勾選「Add Python to PATH」）。

2. 在 PowerShell 裡，切換到你下載這個專案的資料夾，然後執行：

   ```powershell
   .\install.ps1
   ```

3. 看到 `安裝完成！` 的訊息就代表成功了。

### Mac / Linux

1. 打開「終端機（Terminal）」，確認 Python 版本：

   ```bash
   python3 --version
   ```

   需要 `3.10` 以上；沒有的話請到 <https://www.python.org/downloads/> 安裝。

2. 切換到專案資料夾，執行：

   ```bash
   ./install.sh
   ```

3. 看到 `安裝完成！` 的訊息就代表成功了。

> 安裝過程卡住了嗎？看 [`docs/install-troubleshooting.md`](docs/install-troubleshooting.md)。

---

## 第 2 步：啟動工具（最快的方法）

安裝完成後，在同一個終端機視窗輸入一個指令就好——把你的網址接在後面：

```bash
seo-advisor auto https://你的網站.com
```

它會自動判斷該做哪些檢查、跑完所有分析，產出一份**白話懶人包**、完整報告、
以及「會不會花錢」的明細。全程免費、不會花任何錢。

**還沒有網站、想先看看？** 輸入這個看範例（完全免金鑰）：

```bash
seo-advisor auto-demo
```

### 不想記指令？用問答精靈

直接輸入 `seo-advisor`（後面什麼都不加），會有問答精靈一步步引導你，
第一個選項就是「一鍵全自動」：

```text
歡迎使用 Open SEO Advisor
請問你想做什麼？
  1 - 一鍵全自動（給我一個網址，剩下交給我，最推薦）
  2 - 只做 SEO 健檢（掃描一個真實網站）
  3 - 掃描本機資料夾裡的網站原始碼
  4 - 先看一份範例報告（不需要輸入網址）
```

不確定選哪個？直接按 Enter 用預設的 1 就好。

---

## 第 3 步：輸入你的網站

如果你選 `1`，工具會問你網址，直接輸入即可，不需要加 `https://`：

```text
請輸入網站網址（例如 example.com）
> example.com
```

工具會自動幫你補上 `https://`，然後開始掃描，過程中會顯示進度：

```text
第 1/4 步：確認網站連線與基本設定（robots.txt / sitemap.xml）
第 2/4 步：逐頁爬取內容
第 3/4 步：檢查常見 SEO 問題
第 4/4 步：整理報告
```

---

## 第 4 步：打開報告

掃描完成後，工具會告訴你三份報告存在哪裡：

```text
完成！網站健康分數：72/100，共發現 6 項可改善之處。

給非技術人員看的懶人包：./seo-report/report-beginner.md
給工程師/SEO 顧問看的完整技術報告：./seo-report/report.md
給程式或自動化流程用的資料：./seo-report/report.json
```

**新手請先打開 `report-beginner.md`**，用一般的文字編輯器或 Markdown 檢視器打開
即可（例如 VS Code、Typora，或直接用記事本打開也看得懂內容）。

這份報告會用「房屋健檢」的比喻，告訴你：

- 網站現在的健康分數代表什麼意思
- 最該優先處理的 3 件事
- 每個問題該找誰處理（自己看說明，或轉交給工程師）

---

## 看不懂報告裡的名詞怎麼辦？

打開 [`docs/glossary-for-beginners.md`](docs/glossary-for-beginners.md)，裡面用
生活化比喻解釋了 `sitemap`、`canonical`、`robots.txt` 等常見 SEO 術語。

---

## 我想交給工程師處理，該給他看哪份？

給他 `report.md`（完整技術報告）和 `report.json`（機器可讀資料）。這兩份包含
每個問題的詳細證據、受影響的網址、以及驗證修復是否成功的具體步驟。

---

## 下一步：想看更完整的功能說明？

看 [`README.md`](README.md) 了解這個工具的完整能力（顧問／工程師／資安／
文章寫手／外掛開發五大模式），以及 [`docs/roadmap.md`](docs/roadmap.md)
了解目前哪些功能還在開發中。
