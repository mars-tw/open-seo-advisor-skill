---
name: Open SEO Advisor
slug: open-seo-advisor
version: 0.2.5
license: Apache-2.0
description: >
  蒸餾多位資深 SEO 顧問方法論與 Google 官方標準，自動偵測網站全域 SEO 問題，
  並提供顧問／工程師／資安／文章寫手／外掛開發／Meta 廣告優化／產圖素材七種
  模式，協助任何產業、任何規模的網站進行 SEO 健檢、修復、內容產出、廣告優化
  與素材製作。
triggers:
  - "/seo"
  - "/seo-audit"
  - "/seo-fix"
  - "/seo-security"
  - "/seo-write"
  - "/seo-plugin"
  - "/seo-ads"
  - "/seo-image"
  - "幫我做 SEO 健檢"
  - "分析這個網站的 SEO 問題"
  - "幫我看廣告成效"
  - "產生廣告素材"
  - "seo audit"
  - "site health check"
---

# Open SEO Advisor

開源、可攜、不綁定單一廠商 API 的全域 SEO 顧問技能。目標是讓任何人（個人站長、
代理商、企業內部團隊、開源貢獻者）都能用同一套方法論，對任何產業、任何技術棧的
網站做出資深顧問等級的 SEO 診斷、修復、內容產出與外掛開發。

## 安全前提（優先於一切功能）

1. **只處理使用者明確授權的網站、主機、原始碼與帳號**。不得對未授權的第三方網站
   進行任何超出公開頁面讀取以外的操作（不得嘗試登入、繞過驗證、探測漏洞）。
2. **預設 read-only、預設 dry-run**。任何會寫入檔案、部署、修改 DNS/CDN 設定、
   呼叫會產生副作用的 API 的操作，必須先產出「執行計畫」給使用者確認，取得
   明確同意後才可執行。
3. **絕不將憑證、金鑰、token、cookie、`.env` 內容寫入報告或程式碼**。憑證只能
   來自環境變數、OS keychain、使用者當下輸入，且只在記憶體中使用。
4. **最小權限原則**：能用 read-only API 就不用有寫入權限的帳號；能用一次性
   command 就不要求持久 shell 存取。
5. 對正式環境（production）的任何寫入或部署操作，一律要求人工二次確認。

## 七大模式總覽

| 模式 | 觸發 | 目標 | 詳細規格 |
|---|---|---|---|
| 顧問模式 Consultant | `seo-advisor audit consultant` | 全站健檢、產出診斷報告與優先順序 | `docs/modes.md#consultant-mode` |
| 工程師模式 Engineer | `seo-advisor fix engineer` | 自動修復 robots.txt/sitemap/canonical（dry-run 預覽，確認後才寫入，有備份/回滾） | `docs/modes.md#engineer-mode` |
| 資安模式 Security | `seo-advisor security audit` | 被動式資安風險掃描（暴露檔案/目錄列表/cloaking/HTTPS/HSTS/spam/CMS 版本），不做攻擊性測試 | `docs/modes.md#security-mode` |
| 文章寫手模式 Content Writer | `seo-advisor write` | 依 SEO 權威指導原則產出內容 | `docs/content_writer_guide.md` |
| 外掛開發模式 Plugin Dev | `/seo-plugin` | 開發 WordPress 等 CMS 的 SEO 外掛 | `docs/modes.md#plugin-dev-mode` |
| Meta 廣告優化 Meta Ads | `seo-advisor ads` | 診斷 Meta 廣告帳戶、產出優化建議與 dry-run 行動計畫 | `docs/meta_ads_mode.md` |
| 產圖素材 Image Material | `seo-advisor image` | 為廣告/社群/文章產生圖像素材（provider 抽象層） | `docs/image_material_mode.md` |

模式路由邏輯見 `scripts/seo_advisor/router.py`：使用者可用明確指令指定模式，
也可以用自然語言描述需求，由 router 判斷最適合的模式；不確定時一律用
`AskUserQuestion` 式的澄清詢問，不要自行臆測。

## 上層統籌層：AI 矩陣營運系統（AI Matrix Operating System）

在七大模式之上，還有一個「AI 矩陣營運系統」統籌層（`seo-advisor matrix`）：
使用者提出一句目標，NORA 總控會判斷情境、派工給 26 位 AI 工作夥伴角色
（涵蓋策略/行銷/銷售/產品/營運/財務/人資/法務/行政）協作，各角色盡量接到
上述已實作的模式引擎，最後整合成一份可執行交付物。

任何含「發布/寄送/花錢/投放/部署/上架/調整預算」的高風險任務，會被強制
升級為需人工確認且只產計畫。免金鑰試玩：`seo-advisor matrix demo`。
詳見 `docs/ai-matrix-os.md`。

## 目前實作狀態（v0.2.5）

- ✅ **SSHConnector 接進 Consultant CLI + `read_logs`（v0.2.5）**：
  `seo-advisor audit consultant --source ssh --ssh-host ... --ssh-confirm
  "CONNECT host:port"` 可直接對遠端伺服器跑全站 SEO 健檢；`list_urls()`
  改為 BFS 遞迴掃描（三重上限防止過度請求），`fetch_url()` 拒絕
  query/fragment/scheme 等不安全輸入。新增選配的 `read_logs`
  能力：`allowed_log_paths` 白名單 + 與 `read_file()` 相同的
  component-wise walk 防 symlink，log 讀取一律從尾端 tail、有位元組數
  上限，`since` 時間篩選 MVP 尚未支援會直接報錯而非靜默忽略。
- ✅ **WordPressAPIConnector 正式上線（v0.2.4）**：透過 WordPress REST API
  唯讀盤點 posts/pages，並用無認證的公開請求抓取實際渲染後的頁面。
  `capabilities()` 只回報 `{"read_urls"}`；只支援 Application Password
  認證（可選匿名唯讀模式），不做 OAuth/寫入。核心安全機制：REST 回傳的
  `link` 欄位視為 attacker-controlled，`list_urls()`/`fetch_url()` 都做
  scope allowlist 雙重檢查（path 用 segment 邊界比對、www/apex 僅允許
  單層 pair）；認證 REST 請求零 redirect 避免 Basic Auth 洩漏；分頁上限
  不信任伺服器回報的 `X-WP-TotalPages`；預設強制 HTTPS。第二次應用
  NORA×Grok 雙模型交叉辯論流程，兩輪設計辯論後 Grok 同意進入落地，
  落地後由 NORA 複審修正。
- ✅ **SSHConnector 正式上線（v0.2.3）**：透過 SFTP 唯讀讀取使用者已授權
  的遠端伺服器網站檔案，`capabilities()` 只回報 `{"read_files"}`；不做
  log/write/command（避免半套實作）。專案首次引入雙 AI 模型交叉辯論
  流程——除了既有的 NORA（Codex）之外，同時讓 Grok（獨立 CLI）加入直接
  交互辯論，兩個獨立模型互相質疑對方設計，三輪收斂後才進入落地。核心
  安全機制：連線前確認字串驗證必須在任何網路操作之前完成；DNS
  rebinding 防護（單次解析＋預建 socket，避免檢查與連線是兩次獨立解析
  的 TOCTOU）；metadata IP 永遠拒絕；private 網段需明確確認；遠端路徑
  用 component-wise walk 逐層拒絕 symlink（防 jail escape）；讀取白名單
  + 敏感檔名 denylist。落地後兩階段複審（NORA + Grok）各自抓到問題並
  修復（DNS TOCTOU、確認字串發生在連線之後等）。
- ✅ **GitRepoConnector 正式上線（v0.2.2）**：`seo-advisor fix engineer
  --write-mode git-branch` 讓修復結果在使用者已存在的本機 git repo 建立
  新分支+commit（不觸碰目前 working tree），完成後留在新分支上供人工
  review 並自行 push 開 PR，不自動 push、不涉及任何遠端連線或憑證。核心
  安全機制：要求 working tree 完全乾淨才建立分支、暫存區內容嚴格驗證、
  失敗自動復原（reset+切回原分支+刪新分支）、拒絕 `.gitignore` 忽略的
  目標（避免無法回滾的資料遺失）、拒絕 submodule/detached HEAD、未完成
  session 偵測與 repo-level lock。NORA 設計 + 落地後複審抓到 9 項問題
  （中斷後殘留狀態、資料遺失風險、並行操作競爭等）全數修復後發布。
- ✅ **Security Mode 正式上線（v0.2.1）**：`seo-advisor security audit` 被動式
  資安掃描——暴露檔案（.env/.git/備份檔等 17 個內建路徑）、目錄列表、
  Cloaking 粗略比對、TLS 憑證/HSTS/mixed content、SEO spam 跡象、CMS 版本
  暴露提示（不查真實 CVE）。不做任何攻擊性測試。核心安全設計：暴露檔案/
  目錄列表/cloaking 檢查需要 `--confirm-authorized "AUDIT <網域>"` 明確
  授權確認才會執行，`--passive-only` 可跳過確認但只做完全被動的檢查；只用
  內建固定路徑清單，不接受自訂 wordlist。NORA 設計 + 落地後複審抓到 8 項
  問題（敏感路徑跨網域 redirect、內容簽章判斷、rate limit 共享、授權字串
  正規化等）全數修復後發布。
- ✅ **Engineer Mode 正式上線（v0.2.0）**：`seo-advisor fix engineer` 自動修復
  robots.txt 缺失/缺 Sitemap、sitemap.xml 缺失、頁面多重 canonical 衝突三種
  技術 SEO 問題。專案第一個真的會寫入使用者檔案的模式：預設 dry-run 預覽，
  `--apply --confirm "APPLY <plan_id>"` 才真的寫入；套用前自動備份，`fix
  rollback` 可還原，且使用者事後手動編輯過的檔案絕不會被 rollback 覆蓋。
  寫入範圍嚴格白名單（僅 txt/xml/html，永不碰程式邏輯檔案）。NORA 設計 +
  落地後複審抓到 9 項問題（partial-apply rollback、樣板語法風險、路徑
  正規化繞過手法等）全數修復後發布。
- ✅ 深度稽核新角度修復（v0.1.18）：修正爬蟲漏爬 www 子網域頁面的 bug（與先前
  canonical www↔apex 誤報同一類模式，共用 `url_utils.normalize_host`）；
  `docs/roadmap.md` 補齊到 v0.1.17（原本只記錄到 v0.1.2）；`docs/ai-matrix-os.md`
  更新矩陣角色引擎接線現狀（7/26 已接真實引擎，非文件原寫的「後續版本」），
  並加測試鎖住比例與 `roles.yaml` 一致避免再度過時。
- ✅ 辯論下一輪修復（v0.1.17）：HTML 單次解析收斂（技術面分析每頁從解析 5 次
  收斂為 1 次）、autopilot 白名單複核的 CI 保險機制（常數改動未接線會讓 CI 失敗）、
  `methodology.yaml` 加 `last_reviewed` 與時效性免責聲明、auto 對打錯字輸入補
  中性提示（原設計的 heuristic 會誤傷合理單詞目標，改為對所有 matrix fallback
  一律提示，記錄於 CHANGELOG 的設計決策）。
- ✅ 全系統健康度大辯論修復（v0.1.16）：多位 CODEX 分立場（效能/安全/新手體驗/
  開源治理）平行分析並交叉辯論，收斂出供應鏈可追溯性（Dependabot+pip-audit）、
  單次掃描重複請求去重、provider 缺金鑰錯誤處理系統性補強（含跨平台金鑰設定
  指令）、`.collab-rules.md` 移出版控等 4 項修復。誤判澄清 8 項避免資源錯置，
  `SECURITY.md` 新增已知限制段落誠實記錄暫不修復的項目。
- ✅ 新手指令收斂（v0.1.15）：回應「指令太多」的回饋，新手從安裝到看報告全程
  只需 `seo-advisor auto <網址>`（或 `seo-advisor` 進精靈）。精靈簡化成只問一句
  網址（空 Enter 看範例）、懶人包零指令、安裝訊息只給一行、完成訊息明說「不需
  記任何指令」；進階指令保留給熟悉者但不對新手主動展示。經 NORA 傻瓜視角複審。
- ✅ Autopilot 接真實引擎（v0.1.14）：`seo-advisor auto <網址>` 現在**真的會跑
  一次快速 SEO 健檢**（呼叫 Consultant runner），回報真實健康分數/問題數並產出
  真報告，不再只是 plan-only 摘要。概念分離：唯讀免費的分析真跑、會花錢的動作
  仍受同意閘門控制。掃描失敗會優雅降級（其他分析照跑）。對外路徑相對化避免洩漏
  本機使用者名稱。經 NORA 設計 + 複審抓隱私/逾時風險後修正。
- ✅ 廣告↔產圖串接（v0.1.13）：`seo-advisor image from-ads ads-report.json`
  把廣告診斷的素材疲勞/CTR 問題轉成新素材方向 brief（測試痛點/成果/信任型不同
  角度）。成本安全：預設只產 brief 不花錢，要產圖須 `--generate`，低信心機會
  還需 `--confirm-low-confidence`。排除追蹤/預算/受眾等非素材問題。經 NORA 設計 +
  複審抓花錢風險後補閘門。
- ✅ 內容↔顧問串接（v0.1.12）：`seo-advisor write --from-report report.json`
  把顧問報告的 SEO 缺口一鍵轉成針對性寫作 brief（找到問題→直接產內容補洞）。
  萃取邏輯保守防垃圾內容：只轉「內容能解決」的缺口、排除技術/資安問題、批次
  metadata 不寫長文、無缺口時友善停止。經 NORA 設計 + 複審抓風險後修正。
- ✅ SEO 診斷實用度強化（v0.1.11）：Consultant 新增 canonical 跨網域、Open Graph、
  JSON-LD 結構化資料三項檢查（含 www↔apex 正規化避免誤報、noindex/API 頁降噪）；
  Growth 成效分析判斷門檻透明化並標明為可依產業調整的預設值。經 NORA 盤點 +
  複審抓誤報後修正。
- ✅ 深度技術/資安強化（v0.1.10）：NORA 程式碼層級深度稽核 + 多輪複審。修
  P0 SSRF redirect 繞過（每一跳重新檢查、擋 metadata IP）、回應大小上限改真
  串流防 memory DoS、sitemap index 請求放大防護、本地檔案大小上限、sitemap XML
  拒絕 DOCTYPE/ENTITY 防 billion laughs、錯誤訊息 redact 敏感資訊、廣告安全
  政策數值驗證。
- ✅ 新手快速啟用 + UX 優化（v0.1.9）：多視角稽核機器人來回多輪把關；修裸網域
  URL bug（`example.com` 免打 https 即可）、信任文案統一（預設不花錢/不改站，
  付費先同意）、autopilot 誠實標示 execution_mode 並附下一步指令、新增給人看的
  `cost-estimate.md`、完成訊息附「怎麼打開報告」指令、安裝腳本加 Python 版本
  硬擋與免 activate fallback。
- ✅ 紮實度強化（v0.1.8）：能力地圖（`docs/capability-map.md`）、API 契約文件
  （`docs/api-contracts.md`）、CLI taxonomy help、CI 擴充為全 demo smoke +
  wheel 安裝驗證、依賴版本上限、provider 失敗路徑測試、heuristic 報告加推測
  性提醒、修正 autopilot 成本估算永遠 mock 的 bug。
- ✅ 一鍵代操機器人（Autopilot）：`seo-advisor auto <網址或目標>` 一個指令
  自動判斷該跑哪些模組、跑遍分析、產出白話懶人包 + 成本明細 + 待辦清單。
  會花錢/寫入/發布的動作採「一次知情同意」（先給白話成本明細，同意一次才
  執行白名單內安全動作；破壞性/付款/發布等永遠不自動做）。互動精靈第一個
  選項就是一鍵全自動。免金鑰試玩：`seo-advisor auto-demo`。詳見
  `docs/autopilot_mode.md`。
- ✅ 行銷方法論知識庫（中性化蒸餾）：四領域共 50 條可執行檢核原則
  （電商 listing / 付費廣告漏斗 / 內容品牌成長 / 轉換成長駭客），
  不具名、不含課程名或商標，供各模組引用。詳見 `docs/methodology.md`。
- ✅ 電商 Listing 健檢模式（Ecommerce）：運用電商方法論檢核標題/賣點/
  圖片/A+/後端關鍵字/評論/庫存與購買入口/變體，產出健康分數與建議，
  `seo-advisor ecommerce audit/demo`，純邏輯免金鑰。詳見 `docs/ecommerce_mode.md`。
- ✅ AI 矩陣營運系統（統籌層）：NORA 總控 + 26 角色資料驅動 registry、
  關鍵字/行業路由、安全升級（高風險任務強制人工審核+plan-only）、
  mock/generic engine、整合交付、`seo-advisor matrix run/demo/roles`。
  詳見 `docs/ai-matrix-os.md`。
- ✅ 成長行銷模組（Growth）：UTM 歸因規劃與衛生檢查、CRO 落地頁診斷與
  A/B 測試設計、跨渠道成效分析（GA4/GSC/Google Ads read-only + Mock），
  `seo-advisor growth utm/cro/analytics/demo`，全部免金鑰可試玩。
  詳見 `docs/growth_marketing.md`。
- ✅ 顧問模式（Consultant Mode）：HTTP/LocalArchive connector、
  技術面 crawler、Finding/Report schema、Markdown+JSON 報告產出、
  noindex 檢查、非 UTF-8 編碼偵測、category-weighted 健康分數。
  詳見 `docs/architecture.md` 與 `docs/modes.md`。
- ✅ 文章寫手模式（Content Writer Mode）：`LLMProvider` 抽象層
  （Anthropic / OpenAI / Local / Mock）、brief → outline → draft → QA
  四階段流程、`seo-advisor write` 指令。詳見 `docs/content_writer_guide.md`。
- ✅ Meta 廣告優化模式（Meta Ads Mode）：`AdsProvider` 抽象層
  （Meta / Mock）、`AdsSafetyPolicy` 多重預算防護、廣告成效診斷、
  dry-run 行動計畫、`seo-advisor ads audit/plan/demo`。實際代操（動用
  真實預算）預設全鎖，詳見 `docs/meta_ads_mode.md`。
- ✅ 產圖素材模式（Image Material Mode）：`ImageProvider` 抽象層
  （OpenAI / Mock）、合規前置檢查、多變體生成、與 Content Writer 串接、
  `seo-advisor image generate/demo/from-content`。詳見 `docs/image_material_mode.md`。
- ✅ 新手體驗：互動精靈（`seo-advisor` / `seo-advisor start`）、
  URL 自動正規化、人話錯誤訊息、白話文報告（`report-beginner.md`）、
  Demo 模式（`seo-advisor demo`）、一鍵安裝腳本、`QUICKSTART.md`。
- ✅ 資安強化：Connector 層 `SafetyPolicy`（dry-run/capabilities/SSRF
  防護程式化約束）、zip slip 防護、robots.txt 遵循與 rate limit、
  sitemap 爬取範圍限制。詳見 `docs/connector_contract.md`。
- 🚧 工程師／資安／外掛開發模式：介面與 prompt 模板已定義於
  `prompts/`，執行邏輯將於後續版本（v0.2.0 起）逐步實作，
  詳見 `docs/roadmap.md`。

## 快速開始

**最快的用法（連小白都行）**：裝好後執行一鍵指令，剩下交給它——

```bash
seo-advisor auto https://你的網站.com
```

它會自動分析、產出一份白話懶人包 + 成本明細 + 待辦清單。**預設只做分析、
不花錢、不改動你的網站**；真正要花錢或寫入的動作會先給你看明細、同意一次才
執行。想先看範例就跑 `seo-advisor auto-demo`。

**完全不會寫程式？** 執行 `install.ps1`（Windows）或 `install.sh`
（Mac/Linux），再執行 `seo-advisor`，精靈只會問你一句「你的網址」，剩下
全自動；沒有網址直接按 Enter 就看範例。詳見專案根目錄的 `QUICKSTART.md`。

進階指令：

```bash
cd scripts
pip install -e .
seo-advisor audit consultant --url example.com --out ./report
```

或使用本地原始碼包：

```bash
seo-advisor audit consultant --source ./my-website --out ./report
```

不確定怎麼用？直接執行 `seo-advisor demo` 可以先看一份範例報告，
不需要輸入任何網址。

## 目錄導覽

- `docs/capability-map.md`：**能力地圖**——一頁看懂全專案有什麼、實作狀態、怎麼呼叫。
- `docs/api-contracts.md`：給貢獻者的介面契約速查（provider 抽象層、報告慣例等）。
- `docs/architecture.md`：整體架構、Connector 抽象層、資料模型。
- `docs/modes.md`：核心 SEO 模式的完整檢查清單、輸出格式、外部資料來源。
- `docs/connector_contract.md`：WebsiteConnector 介面規格與資安要求。
- `docs/content_writer_guide.md`：SEO 寫作品質規範與 prompt 模板。
- `docs/i18n_seo_guide.md`：跨產業與國際化 SEO 檢查重點。
- `docs/roadmap.md`：MVP 到 1.0 的實作路線圖。
- `schemas/`：Finding／Report／Connector 的 JSON Schema。
- `config/`：預設檢核規則、評分權重、產業與地區設定檔。
- `prompts/`：各模式的 system prompt 模板。
- `scripts/seo_advisor/`：Python 實作本體。

## 貢獻與授權

本專案採 **Apache-2.0** 授權，開源給全球任何人使用、修改與再散布，詳見
`LICENSE` 與 `CONTRIBUTING.md`。歡迎針對不同產業、語言、CMS 或雲端平台
貢獻新的 connector、analyzer、fixer 或產業設定檔。
