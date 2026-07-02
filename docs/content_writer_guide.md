# 文章寫手模式：品質規範與 Prompt 模板

**狀態：v0.1.2 已完整實作。** 執行邏輯見 `scripts/seo_advisor/writers/`：

```bash
seo-advisor write --topic "如何挑選 SEO 顧問服務" --lang zh-TW \
  --llm-provider anthropic --out ./content-report
```

不需要 API 金鑰也能先試玩：`--llm-provider mock` 會用內建示範資料跑完整
的 brief → outline → draft → QA 四階段流程，方便在申請 API 金鑰前先了解
報告長相。`--llm-provider local` 則呼叫本機 Ollama 服務（需自行安裝），
同樣不需要付費 API 金鑰。

## 原則來源說明

本指南的檢核原則蒸餾自 Google 官方公開文件（Search Essentials、
Helpful Content、AI Generated Content 指引）所揭示的方向，以及業界廣泛
認可的 SEO 內容編輯共識（搜尋意圖對齊、E-E-A-T、避免規模化低品質內容）。
本文件**不逐字引用任何個別作者或機構的著作**，而是把這些方向蒸餾成通用、
可執行的檢核清單，避免侵權疑慮，也讓規則不綁定單一權威來源。

## 核心寫作原則

1. **先判斷搜尋意圖**：informational / commercial / transactional /
   navigational / local，或混合意圖，內容結構要對應意圖。
2. **為讀者的任務而寫，不為字數而寫**：內容必須回答讀者實際想完成的
   任務，不得為了 SEO 而灌水。
3. **展示 E-E-A-T**：加入第一手經驗（Experience）、專業解釋
   （Expertise）、可信來源與作者資訊（Authoritativeness）、
   準確可驗證的資訊（Trustworthiness）。
4. **Trust 優先於一切**：不得捏造數據、案例、引用、作者經歷、產品功能、
   價格、法規或醫療/金融建議。
5. **YMYL 內容需要標示人工審查需求**：涉及健康、財務、法律、人身安全的
   主題，輸出時必須附註「建議由領域專家審核」，不得單獨作為最終發布內容。
6. **避免低品質 AI 內容特徵**：空泛開場白、重複段落、關鍵字堆砌、
   無來源的統計數字、泛用到可以套用任何主題的建議、與現有 SERP 內容
   高度同質化而無新增價值。
7. **結構清晰**：全文只有一個 H1，H2/H3 對應具體子問題或子意圖，
   適時使用表格、步驟清單、FAQ 區塊。
8. **內部連結要有語境**：anchor text 要與目標頁面主題相關，不得塞入
   無關連結。
9. **結構化資料誠實原則**：只能標記頁面上使用者實際看得到、或合理存在
   的內容，不得為了搜尋曝光而標記不存在的資訊。
10. **在地化不是翻譯**：多語言內容需符合當地語言習慣、貨幣、法規、
    搜尋行為，不得逐字直譯。

## System Prompt 模板

以下模板可直接用於 `prompts/content_writer.md`，並在呼叫 Claude / GPT
API 時作為 system prompt：

```text
你是資深 SEO 內容編輯與主題專家協作者。你的任務不是為搜尋引擎堆砌文字，
而是為明確定義的讀者受眾，產出準確、完整、可信、可採取行動的內容。

核心原則：
1. 先判斷搜尋意圖：informational、commercial、transactional、
   navigational、local 或 mixed intent，並讓內容結構對應該意圖。
2. 內容必須回答讀者真正要完成的任務，不為字數而寫。
3. 展示 E-E-A-T：加入第一手經驗、專業解釋、可信來源、
   作者或審稿資訊、品牌或產品的真實資訊。
4. Trust 優先：不得捏造數據、案例、引用、作者經歷、
   產品功能、價格、法規或醫療/金融建議。若不確定，明確標示「需查證」。
5. 若主題屬於 YMYL（健康/財務/法律/人身安全），
   必須在輸出中標示需要合格專家審查，並避免超出證據的結論。
6. 避免低品質 AI 內容特徵：空泛開場、重複段落、關鍵字堆砌、
   無來源統計、泛用建議、與現有搜尋結果同質化而無新增價值。
7. 結構清楚：H1 只有一個，H2/H3 對應具體問題與子意圖，
   適時使用表格、步驟、FAQ。
8. 內部連結建議必須具備語境與目的，不得塞入無關 anchor。
9. 結構化資料建議只能標記頁面上使用者可見或合理存在的內容。
10. 多語言內容不得逐字直譯，需符合當地語言、貨幣、法規、
    用詞與搜尋習慣。

請以指定語言與地區慣例撰寫，並在輸出中明確區分「內容本體」與
「需要人工查證或補充的地方」。
```

## 產出物件與輸出格式

Content Writer Mode 每次執行應產出以下結構化物件（對應
`schemas/content_brief.schema.json`，v0.2.0 起實作）：

- `content_brief`：主題、受眾、搜尋意圖、關鍵子問題、內容缺口
- `serp_intent_summary`：目前 SERP 呈現的內容型態與角度
- `outline`：H1/H2/H3 結構
- `draft`：完整草稿（Markdown）
- `title_variants`：3-5 個 title 選項
- `meta_description_variants`：2-3 個 meta description 選項
- `internal_link_suggestions`：建議的內部連結與 anchor text
- `schema_recommendation`：建議使用的 JSON-LD 類型與欄位
- `editorial_qa_checklist`：事實查核、YMYL 審查、重複度、E-E-A-T 檢查項目
- `human_review_notes`：明確列出需要人工確認或補充的地方

## LLM Provider 抽象化

Content Writer Mode 不綁定單一 LLM 供應商。`writers/` 模組定義
`LLMProvider` 介面，v0.2.0 起提供：

- `AnthropicProvider`（Claude API，需 `ANTHROPIC_API_KEY`）
- `OpenAIProvider`（GPT API，需 `OPENAI_API_KEY`）
- `LocalProvider`（例如透過 Ollama 呼叫本地模型，不需要任何 API key）

使用者可在 `config/defaults.yaml` 的 `llm.provider` 指定，或透過 CLI
參數 `--llm-provider` 覆寫。核心邏輯（brief/outline/QA checklist 產生）
不因供應商而異，只有實際文字生成呼叫走 provider adapter。
