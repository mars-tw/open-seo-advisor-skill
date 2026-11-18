# 第一次使用商業 SEO 技能

## 貼上或安裝

想直接試用，複製[五步提示詞](workflow.md)的整個文字區塊，貼到 Claude Code 或 Codex，附上銷售市場與資料位置。想讓同一個網站專案下次也能用，從本專案複製整個 `skills/commercial-seo/` 資料夾（含 `references/`），依使用的工具擇一放置。兩種方式都可直接使用匯出檔。

| 工具 | 複製到網站專案下的位置 | 開始對話 |
| --- | --- | --- |
| Codex | `.agents/skills/commercial-seo/` | `$commercial-seo 請先從台灣市場挑選商業關鍵字。` |
| Claude Code | `.claude/skills/commercial-seo/` | `/commercial-seo 請先從台灣市場挑選商業關鍵字。` |

若專案使用完整的 Open SEO Advisor，也可以直接請它「使用商業 SEO 五步流程分析這個關鍵字」。[Codex 技能安裝](https://developers.openai.com/codex/skills/)｜[Claude Code 技能安裝](https://code.claude.com/docs/en/skills)

## 選擇這次使用的模型

- **Codex** 可在模型選單挑選帳號當前可用的旗艦。若清單列出 GPT-6.2 Astra，適合多市場選頁、競品比較和重要頁面終審。CLI 可用 `codex -m gpt-6.2-astra` 開始新工作階段。日後可直接改選更新的模型。[OpenAI 模型與選擇方式](https://learn.chatgpt.com/docs/models)
- **Claude Code** 可用 `/model` 查看帳號選項。想重現原文的 Fable 5.2，先用 `claude --version` 確認是 2.1.321 以上。若需要更新，依安裝方式執行 `claude update` 或套件管理器的更新指令。再用 `claude --model claude-fable-5-2` 指定該版；`/model fable` 使用當時該別名對應的版本。使用資格依帳號方案而定。[Claude 模型設定](https://code.claude.com/docs/en/model-config)｜[Fable 版本需求](https://support.claude.com/en/articles/15424964-claude-fable-models-on-your-plan)

## 準備資料

| 用途 | 最少要提供什麼 | 現在可以做什麼判斷 |
| --- | --- | --- |
| 找出買家正在搜尋的詞 | GSC 資源、日期範圍、國家、搜尋類型、裝置條件、查詢、點擊、曝光、平均排名 | 找本站已有曝光的詞。搜尋量另外取自 Keyword Planner 等工具，保留地區、統計期間及工具傳回的數值或區間。 |
| 判斷某個詞應該優化哪頁 | 在 GSC「搜尋結果」針對該詞使用「完全相符的查詢」篩選，再匯出「網頁」分頁及篩選條件；或提供 API 的 `query`、`page` 同列資料。另附站內可索引頁清冊 | 查到目前是哪個網址承接。匿名查詢與匯出筆數上限會影響可見資料。[Search Console 資料範圍](https://developers.google.com/webmaster-tools/v1/how-tos/all-your-data) |
| 比較搜尋結果 | 當地同一查詢、日期、語言、裝置和前十個自然結果，附順位與 URL。前三名另附可開啟的網址、內文或可讀的頁面擷取 | 結果頁截圖可以辨認頁型；讀到實際頁面才能比較選購資訊。 |
| 寫交易頁與判讀成交 | 商品或服務清冊、核定規格、價格與供貨資料或詢價條件、相關站內網址。有成交資料時用按市場彙總的訂單或 CRM 報表 | 寫出可核對的交易條件。純詢價商品可列產品資料，Google 商品摘要與商家資訊各有資格條件。[Google 商品結構化資料](https://developers.google.com/search/docs/appearance/structured-data/product) |

## 選用 ChatSEO MCP

在自己的 ChatSEO 帳號選定網站、連接對應的 GSC 資源，確認方案支援 MCP。依使用的工具選一組指令。在 Claude Code 用 `/mcp` 完成授權；在 Codex 若新增伺服器時已完成登入，就可略過登入指令。[ChatSEO 連線與帳號授權](https://chatseo.app/help/connecting-chatseo-to-claude-code-via-mcp)｜[Codex MCP 設定](https://developers.openai.com/codex/mcp/)

```sh
# Claude Code
claude mcp add --transport http chatseo https://api.chatseo.app/mcp
```

```sh
# Codex CLI
codex mcp add chatseo --url https://api.chatseo.app/mcp
codex mcp login chatseo
```

連線後先用唯讀查詢讀回選定的網站與日期，核對市場和實際回傳欄位。關鍵字搜尋量、SERP 或競品內文若取不到，可補交上表對應資料。

## 流程來源

Nicholas Dulait 在 2026 年 11 月 10 日以 Fable 5.2 示範從關鍵字、競品比較到週一檢視的做法。本版依使用者整理及可讀的英文收錄內容重寫提示詞。作者用一節說明推理強度，本版把強度分配到各步，並把確認既有排名頁獨立為第 2 步。市場與產業指南、詢價商品處理、證據欄位及跨工具設定由本專案補充。[作者原帖](https://x.com/NicholasDulait/status/2120063043614716174)｜[X Article](https://x.com/i/article/2120059230547795968)｜[英文收錄版](https://haowenji.com/articles/x-2120059230547795968)
