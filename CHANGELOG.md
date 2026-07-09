# Changelog

本專案採用 [Semantic Versioning](https://semver.org/)。

## [0.2.2] - Unreleased

**GitRepoConnector 正式上線**（`docs/roadmap.md` v0.2.0 第三批）：Engineer
Mode 新增 `--write-mode git-branch` 選項，讓修復結果產出可直接 `git push`
開 PR 的分支+commit，而不觸碰使用者目前的 working tree。由 NORA 設計、
CLAUDE 審核落地，NORA 再對落地後的實作做一輪批判性複審，逐項修復後發布。

### 新增：`seo-advisor fix engineer --write-mode git-branch`

- 在使用者已存在的本機 git repo 建立新分支（`seo-advisor/fix-<finding_id>`），
  把修復內容 commit 進去（commit message 含 finding_id/plan_id 方便追溯），
  不自動 push、不自動開 PR——完成後留在新分支上，由使用者自行 review 並
  `git push -u origin <branch>`。
- 只支援本機已存在的 git repo，不涉及任何遠端連線、SSH key 或 HTTPS 認證。

### 安全機制

- **要求 working tree 完全乾淨**才會建立新分支，比 direct 模式更保守，
  避免把使用者尚未提交的變更意外混進 commit。
- **暫存區內容驗證**：commit 前確認 staged 的檔案精確等於這次修復的目標
  清單，不符就自動中止並復原，避免任何非預期檔案被一併提交。
- **失敗自動復原**：任何步驟失敗都會把 repo 恢復到套用前的狀態（reset
  到 base commit、切回原分支、刪除新分支），只在「這個分支是本次操作
  剛建立」的前提下執行，不影響使用者既有的任何分支。
- **未完成 session 偵測**：若前一次操作中途被中斷（例如 Ctrl+C），下一次
  執行會偵測到殘留狀態並拒絕繼續，避免在不確定的狀態上疊加操作。
- **.gitignore 保護**：若修復目標剛好是被 `.gitignore` 忽略的既有檔案，
  拒絕整個操作——這種檔案就算失敗復原，git 也無法恢復其原始內容（沒有
  版本歷史可還原），避免造成無法挽回的資料遺失。
- **拒絕 submodule 內的檔案、拒絕 detached HEAD 狀態**。

### 過程中的把關

落地後請 NORA 做一輪批判性複審，抓到 9 項問題並全數修復：中斷後的殘留
session 偵測、`.gitignore` 檔案覆寫後無法回滾的資料遺失風險、detached
HEAD 誤判、暫存區路徑比對的 NUL 字元處理、並行操作的 repo-level lock、
submodule 路徑拒絕、`.git` 目錄位置改用 `git rev-parse --git-dir` 取得
（而非硬編碼假設）、`LocalArchiveConnector` 掃描排除 `.git/`/`node_modules/`、
分支已存在時的錯誤訊息補充明確的處理指引（詳見 CHANGELOG 開發記錄）。

### 測試

新增約 18 個測試（GitRepoConnector 安全邊界、runner 整合、
LocalArchiveConnector 工具目錄排除），總計 395 個測試全過，ruff lint 乾淨。

## [0.2.1] - Unreleased

**Security Mode 正式上線**（`docs/roadmap.md` v0.2.0 第二批）：被動式、非
破壞性的資安風險掃描，不做任何攻擊性測試。由 NORA 設計授權邊界與檢查架構、
CLAUDE 審核落地，NORA 再對落地後的實作做一輪批判性複審，逐項修復後發布。

### 新增：Security Mode（`seo-advisor security audit`）

- 檢查項目：暴露檔案偵測（.env/.git/備份檔等 17 個內建路徑）、目錄列表偵測、
  Cloaking 粗略比對（一般 UA vs Googlebot UA 內容差異）、TLS 憑證有效性/
  到期/版本、HSTS、mixed content、SEO spam 跡象（CSS 隱藏文字/連結）、CMS
  版本暴露提示（不查真實 CVE，只誠實提示版本號是否公開可見）。
- 輸出 Severity（S0 危急～S3 低風險）、SEO 影響面向、證據、修復建議、是否
  需要更換憑證。

### 授權邊界（核心安全設計）

- 暴露檔案/目錄列表/cloaking 比對本質上是對目標網站發送探測性請求，預設
  需要 `--confirm-authorized "AUDIT <網域>"` 明確確認才會執行；`--passive-only`
  可跳過確認，但只執行完全不發送額外請求的被動檢查。
- 只用內建的固定路徑清單，不接受使用者自訂 wordlist，避免被當成通用掃描
  工具濫用。
- 暴露檔案內容不下載完整檔案、不存進報告——只有狀態碼/長度/是否符合內容
  簽章等中性資訊；已知敏感路徑連極短的內容摘要都不保留。

### 過程中的把關

實作中新增 `HTTPConnector.probe_path()`，複用既有的 SSRF 防護與 rate
limiter。落地後請 NORA 做一輪批判性複審，抓到 8 項問題並全數修復：敏感
路徑 probe 禁止跨網域追隨 redirect（避免對未授權第三方發送探測）、暴露
檔案改用內容簽章判斷而非只憑 200 狀態碼（降低 SPA/WAF 造成的高誤報率）、
多個 HTTPConnector 共享同一個 RateLimiter（避免速率被稀釋）、授權確認字串
綁定正規化後的網域（www/apex 視為同一目標、非預設 port 明確標示）、
`--passive-only` 一併跳過 cloaking 比對、全域拒絕含帳密的 URL、補充高
價值探測路徑。

### 測試

新增約 42 個測試，總計 376 個測試全過，ruff lint 乾淨。

## [0.2.0] - Unreleased

**Engineer Mode 正式上線**（`docs/roadmap.md` v0.2.0 第一批）：這是專案第一個
「真的會寫入使用者檔案」的模式，過去所有模式都是 read-only 或 plan-only。
由 NORA 設計整體架構與安全機制、CLAUDE（CEO/審核端）審核並落地，NORA 再對
落地後的實作做一輪批判性複審，逐項修復複審抓到的問題後才發布。

### 新增：Engineer Mode（`seo-advisor fix engineer` / `fix rollback`）

- 自動修復三種技術 SEO 問題：robots.txt 缺失/缺 Sitemap 宣告、sitemap.xml
  缺失（用已爬取頁面建立）、頁面多重 canonical 標籤衝突。
- 流程：列出可修復的 Finding →（可選 `--from-report` 讀既有顧問報告，
  否則就地跑一次快速掃描）→ 產出 PatchPlan（dry-run 預覽 diff/風險等級/
  警告）→ 人工確認後 `--apply --confirm "APPLY <plan_id>"` 才真的寫入。
- `--site-url` 提供正式站台網址時，sitemap/robots.txt 產出絕對 URL；
  不提供時明確警告內容只是相對路徑。
- 只支援本地原始碼包/目錄（`--source`），不支援直接修改線上網站——網址類
  的寫入能力（SSH/WordPress API）屬於後續批次。

### 安全機制

- **雙重確認**：`--apply` 加 `--confirm "APPLY <plan_id>"`，plan_id 綁定
  特定計畫，不是可重複套用的萬用通關密語。
- **備份與回滾**：套用前自動備份到 `.seo-advisor/backups/<id>/`，`fix
  rollback` 可還原；**若使用者在套用之後又手動編輯過檔案，rollback 會比對
  hash 偵測到並跳過該檔案，絕不覆蓋使用者的後續改動**。
- **寫入範圍白名單**：只允許 `.txt`/`.xml`/`.html`/`.htm`，一律拒絕任何
  程式邏輯檔案（`.py`/`.php`/`.js`/`.ts`/`.sh`）；黑名單擋下 `.env`/
  `.git/`/`wp-config.php`/`.ssh/`/Engineer Mode 自己的備份目錄；路徑比對
  做 Unicode 正規化與 Windows 保留裝置名稱檢查。
- **atomic write**：寫 temp file（`tempfile.mkstemp` 保證唯一）→ `os.replace`
  → 寫入後重新讀取驗證 hash，確保沒有半途損毀。
- **樣板語法偵測**：canonical fixer 若偵測到頁面含 Jinja/Django/PHP 等樣板
  語法，不自動改寫（重新序列化整份 HTML 有意外改動樣板結構的風險），只
  警告請手動處理。
- **partial apply 仍可正確 rollback**：多檔案套用時若中途失敗，已成功寫入
  的檔案仍可被正確識別並還原（逐檔案增量記錄 hash，而非全部完成才記錄）。

### 過程中的兩輪把關

實作中自行發現並修正 3 個問題（`can_fix()` 誤判邏輯用了粗略分類、rollback
hash 比對方向錯誤、URL→本地路徑轉換沒處理乾淨網址）。落地後請 NORA 做一輪
批判性複審，另抓到 9 項問題（partial-apply rollback 缺口、新建檔案 rollback
完整性、sitemap/canonical 需要正式網址、路徑白名單繞過手法、備份目錄自我
寫入風險、備份 ID 碰撞、temp file 命名碰撞、樣板語法風險、manifest 路徑
正規化），全部驗證後修復。

### 測試

新增約 30 個測試（LocalArchiveConnector 寫入安全機制、fixers 各模組、
runner 端到端流程、rollback 安全判斷），總計 334 個測試全過，ruff lint 乾淨。

## [0.1.18] - Unreleased

單一 agent 深度稽核新角度：測試品質/邊界情況覆蓋、功能完整度 vs 文件承諾
（前兩輪已覆蓋效能/安全/新手體驗/開源治理四立場，這次刻意換不同視角）。

### 修正

- **【P1】爬蟲漏爬 www 子網域頁面**：`HTTPConnector.is_url_in_scope` 與
  `crawler._same_site` 過去用精確字串比對 host，若目標網站的 www/apex 兩個
  版本都能直接訪問、沒有互相 redirect，會把同站的 www 頁面誤判為外部連結而
  完全跳過（漏爬）。這與先前修過的 canonical www↔apex 誤報是同一類 bug 模式，
  只是換了「連結範圍判斷」這個位置存在。新增共用的 `url_utils.normalize_host`，
  讓爬取層（`http.py`/`crawler.py`）與分析層（`analyzers/technical.py`）用
  同一套正規化邏輯比對，並翻正了一條原本斷言「www 版本不在範圍內」的既有
  測試（那條測試把有缺陷的行為當正確答案鎖住了）。

### 文件

- **`docs/roadmap.md` 補齊到 v0.1.17**：原本只記錄到 v0.1.2，完全沒反映後續
  15 個版本做出來的 ads/images/growth/ecommerce/matrix/autopilot 六大功能
  區塊，會讓新讀者/貢獻者誤以為專案還很初期。已用 CHANGELOG 摘要回填，並
  重新核實 v0.2.0 之後的規劃是否仍準確（結構化資料驗證項目補充說明 v0.1.11
  已完成語法檢查，本項指更完整的 Schema.org 型別驗證）。
- **`docs/ai-matrix-os.md` 更新引擎接線現狀**：原文寫「IRIS → 顧問模式引擎
  （後續版本接上）」，但這件事已經做了——目前 26 角色中 7 個（27%）已接真實
  專屬引擎（IRIS/MAYA/LUNA/ECHO/CODY/JACK/PIXEL），文件卻還停留在 v0.1.4
  當時的骨架敘述。已更新為表格呈現實際接線狀態；`docs/capability-map.md`
  同步更新一致的比例說明。新增測試鎖住這個比例與 `roles.yaml` 一致，未來
  角色接線變動卻忘記同步文件時會被測試擋下。

### 測試

新增 3 個測試（www/apex 範圍判斷 2 項、matrix 引擎比例與文件一致性 1 項），
總計 306 個測試全過，ruff lint 乾淨。

## [0.1.17] - Unreleased

執行全系統健康度辯論（v0.1.16）當時被列入「下一輪」的 4 項建議。

### 修正

- **HTML 單次解析收斂**：技術面分析（title/meta/H1/canonical 重複、noindex、
  canonical 跨網域、Open Graph、JSON-LD）過去對同一頁面各自呼叫
  `BeautifulSoup(html, "lxml")`，每頁被解析 5 次；新增 `_parsed_pages()` 一次性
  解析並共用，同一頁現在只解析 1 次，加測試證明。
- **autopilot 白名單/黑名單複核的 CI 保險機制**：`autopilot/safety.py` 定義的
  `is_auto_executable()` 目前未被 `_execute_safe_actions()` 呼叫（因
  `_MVP_FORCE_PLAN_ONLY` 恆為 `True` 而暫無實益），新增機制性測試——一旦有人
  把這個常數改為 `False` 卻忘記讓 executor 接上複核，CI 會立即失敗並提示原因。
- **`methodology.yaml` 加 `last_reviewed` 與時效性免責聲明**：四個領域各自標記
  最後人工審查日期；`docs/methodology.md` 新增段落說明這些方法論「效果因產業/
  市場/時機而異、不構成成效保證」，並提醒平台政策變動時以官方最新規範為準。
- **auto 指令對「像是打錯字」輸入的體驗改善**：新手把網址打錯導致完全不像
  網址（例如漏了 `.com`）時，過去會落入 `matrix` 通用骨架 fallback，且用「已由
  NORA 總控判斷」這種成功語氣，容易讓人誤以為健檢已完成而不會回頭檢查輸入。
  現在會額外提示「若你原本想輸入的是網址，請確認網址完整」。

### 設計決策（原方案評估後調整，記錄以避免重複走同一條死路）

原辯論建議是「值測輸入含網域字元特徵但解析失敗時才提示」，實作時發現這個
heuristic 無法區分「打錯字的網域」與「合理的單詞目標」——任何英文單字加上
`.com` 都會通過網域格式檢查，若用這個訊號判斷，會連 `growth`、`seo`、`help`
這類合理的模糊目標都一併誤判成「你是不是網址打錯字」。改為對所有
`matrix` fallback 一律加上中性提示（不斷言、只提醒使用者自行核對），放在
`highlights`（完整報告才展開）而非 `summary`（懶人包會直接顯示），避免對
合理目標的使用者造成不必要的困惑或武斷語氣。

### 測試

新增 6 個測試（HTML 解析次數 1 項、autopilot 安全閘門機制 1 項、
methodology last_reviewed 格式 1 項、打錯字提示 1 項、既有測試調整 2 項），
總計 303 個測試全過，ruff lint 乾淨。

## [0.1.16] - Unreleased

全系統健康度大辯論：多位 CODEX 分別扮演效能派、安全派、新手體驗派、開源治理派
四種立場，平行深度分析現有系統並交叉質疑彼此的發現（28 項發現、經交叉辯論後
8 項被裁定「誇大或不成立」而不採納），最後由仲裁者收斂出 3 項應立即修復的項目，
CLAUDE（CEO/審核端）審核執行，並額外發現並修復第 4 項（`.collab-rules.md`
誤被公開）。這是「多方交鋒收斂」而非單向派工審核的協作模式首次嘗試。

### 修正

- **供應鏈可追溯性**：新增 `.github/dependabot.yml`（每週檢查 Python 依賴與
  GitHub Actions 版本）；CI 新增 `security-audit` job，用 `pip-audit` 掃描已知
  漏洞、並把 `pip freeze` 結果存成 build artifact——過去 CI 綠燈無法回溯「測的
  是哪個版本組合」，也沒有任何 CVE 示警機制，現在補上。
- **單次掃描的重複請求**：`HTTPConnector` 對 robots.txt/sitemap.xml/首頁的內容
  在同一次掃描中會被 `probe()`、`crawl_site`、`list_urls()` 各自重複抓取
  （sitemap.xml 甚至被抓 3 次），新增請求層級快取後同一路徑只真正發送一次，
  減少不必要的 HTTP round trip，也減輕對被掃描網站的負擔。
- **provider 缺金鑰的錯誤處理系統性補強**：`LLMProviderError` /
  `ImageProviderError` / `AdsProviderError` / `AnalyticsProviderError` 過去
  未被 `translate_exception` 接住，會落入嚇人的「執行過程中發生未預期的問題」；
  同時 4 處 provider（Anthropic/OpenAI 文字/OpenAI 圖像/Meta）教使用者用
  `export FOO=bar` 設定金鑰，這在 Windows PowerShell 完全打不動。新增
  `env_hints.set_env_var_hint()` 依平台給正確指令（Windows 用 `$env:`，不用
  會把金鑰持久寫入登錄檔的 `setx`），並把這 4 類例外接進已知錯誤清單。
- **`--debug` 模式安全設定明確化**：`pretty_exceptions_show_locals=False`
  明確寫入 CLI 設定（避免依賴 typer 未來版本預設值不變），並加 regression
  test 鎖住，防止未來無聲引入「traceback 印出每層 stack frame 區域變數
  （可能含 API 金鑰）」的風險。
- **`.collab-rules.md` 移出版控**：這份檔案自己聲明「非對外開源文件」卻被
  commit 進公開 repo，屬於零成本但觀感風險不小的疏漏，已移除並加入 `.gitignore`。

### 文件

- `SECURITY.md` 新增「已知限制」段落，誠實記錄兩項評估後判斷「現階段風險可
  接受、暫不修復」的項目（SSRF 的 DNS rebinding TOCTOU 窗口、`LocalProvider`
  未套用 SSRF 檢查），並說明重新評估的觸發條件。

### 未採納（辯論後裁定誇大或不成立，記錄以避免重複提出）

DNS rebinding TOCTOU 需要攻擊者控制惡意網域且精準命中時間窗口，單機 CLI 情境
操作者與潛在受害者是同一人，投入產出比不成立；`image from-ads` 的低信心閘門
只在該指令生效，被認為是「防自動化鏈路盲目信任」而非「杜絕使用者主動決定」，
語意調整即可不需架構調整；全域 i18n、CODEOWNERS、同意閘門改中文確認句、單一
作者治理模式等，皆屬時間尺度或問題性質判斷後不成立或應緩議的項目。

### 測試

新增 12 個測試（HTTP 請求去重 3 項、provider 例外識別 4 項、跨平台金鑰提示
4 項、debug 安全設定 1 項），總計 299 個測試全過，ruff lint 乾淨。

## [0.1.15] - Unreleased

新手指令收斂：一個指令就好。回應「指令太多、很多是新手」的回饋，把新手從頭到尾
看到的指令量大幅收斂——新手只需 `seo-advisor auto <網址>`（或直接 `seo-advisor`
進精靈），進階指令保留給熟悉的使用者但不再對新手到處冒出來。經 NORA 傻瓜使用者
視角複審後補齊安裝訊息/精靈等第一接觸點。

### 收斂

- **互動精靈簡化**：從「4 個選項（列出各模式）」改成只問一件事——你的網址；
  沒有網址直接按 Enter 就自動看範例。新手不必理解 audit/write/ads… 各是什麼。
- **報告懶人包零指令**：autopilot 白話懶人包不再於每個模組後面附
  `seo-advisor xxx` 指令（實測指令數 0）；進階指令改存 `advanced_hint`，只在
  完整報告顯示（給工程/行銷夥伴）。
- **安裝腳本成功訊息**：從列 4 條指令收斂成「只做一件事：複製這一行看範例」，
  其餘進階用法指向 QUICKSTART。
- **完成訊息**：auto 與精靈跑完只叫使用者「打開這份最好懂的報告」，並明說
  「你不需要記任何指令」；不再附 `--approve` 等指令。
- **CLI help**：從列 8 個模組的三層 taxonomy，改成「新手只要記
  `seo-advisor auto <網址>`」，進階指令一句話帶過指向能力地圖。

### 保留（避免收斂過頭）

- 懶人包仍明確告訴新手「完成了什麼、該打開哪個檔案、需要更深入時交給誰」。
- 進階使用者的完整指令全部保留，只是不對新手主動展示。

### 測試

清理 wizard 死碼，總計 287 測試全過，ruff lint 乾淨。

## [0.1.14] - Unreleased

升級：autopilot 接真實引擎（consultant 先行）。由 NORA 設計，CLAUDE（CEO/審核端）
審核後實作，經 NORA 第 2 輪複審抓出成功路徑的隱私與逾時風險後修正。

### 升級：`seo-advisor auto <網址>` 現在真的會跑 SEO 健檢

autopilot 對網址目標不再只給 plan-only 摘要，而是**實際呼叫 Consultant runner
做一次快速健檢**，回報真實的健康分數、問題數，並產出真的 SEO 報告——旗艦入口
從「demo 級摘要」升級為「真正可用」。

- 概念分離：`_MVP_FORCE_PLAN_ONLY` 現在只管「會花錢/寫入的動作」（產圖/產文/
  廣告仍 plan-only）；**唯讀、免費、安全的 consultant 分析本來就該真跑**，不再被
  一刀擋成 plan-only。安全性不變——花錢動作依然鎖著、成本明細不變、首屏「預設
  不花錢」仍成立。
- 快速健檢：預設 max_urls=30、max_depth=3、per-request timeout 8 秒，讓 auto 快速
  出結果；報告提示深掃請用 `seo-advisor audit consultant --max-urls 200`。
- 錯誤降級：真掃描失敗（連不上、逾時、被 SSRF 防護擋、被 bot 封鎖）時，consultant
  標「未完成（可稍後重試）」，**autopilot 不會整體崩潰、其他分析照常進行**。

### 安全 / 隱私

- SSRF 防護在這條新路徑上仍生效（consultant HTTP 一律走 `HTTPConnector._safe_get`）。
- **對外報告路徑相對化**：module report_paths 改成相對 out_dir 的路徑，避免絕對
  路徑洩漏本機使用者名稱（如 `C:\Users\姓名`）。失敗原因訊息經 `redact_secrets`。

### 測試 / CI

新增 autopilot 測試（consultant 真跑產真報告、failed 降級不崩且遮蔽帳密、路徑
相對化不洩漏）。CI 的 auto-demo smoke 現在會實際跑真 consultant。總計 287 測試全過。

## [0.1.13] - Unreleased

模組串接：廣告 ↔ 產圖。由 NORA 設計萃取邏輯，CLAUDE（CEO/審核端）收斂並
強化成本安全後實作，經 NORA 第 2 輪複審抓出「低信心仍會花錢」風險後補閘門。

### 新增：`seo-advisor image from-ads`

把廣告診斷發現的素材問題（素材疲勞、CTR 下降）一鍵轉成新素材方向 brief——
建議測試痛點/成果/信任型等不同創意角度，而非換顏色（延續蒸餾的付費廣告方法論）。

```bash
seo-advisor ads demo --out ./ads
seo-advisor image from-ads --ads-report ./ads/ads-report.json
```

### 成本安全（核心設計）

- **預設只產 brief（image-brief.md/json），不呼叫 API、不花錢**；要真產圖必須
  明確加 `--generate`。
- **低信心閘門**：若主要素材機會信心較低（performance/audience 類、或缺
  frequency/CTR 佐證的 creative_fatigue），加了 `--generate` 也要再加
  `--confirm-low-confidence` 才產圖，避免白花錢產無用素材。
- `--provider mock` 永遠免費。

### 保守的萃取邏輯（不誤導產無用素材）

- 只有「產新素材能解決」的問題才納入（creative_fatigue，或含素材訊號的 performance）。
- tracking / budget / structure 一律排除——這些不是產圖能修的。
- ROAS 低但無 CTR/素材訊號 → 排除（可能是追蹤/落地頁問題）。
- performance/audience 納入時一律標「需人工確認」。
- `ads demo` 一併輸出 `ads-report.json` 供直接串接。

### 測試 / CI

新增 10 個 ads_bridge 測試（含技術問題排除、低信心標記、安全提示），CI 增加
`image from-ads` 串接 smoke。總計 285 測試全過。

## [0.1.12] - Unreleased

模組串接：內容 ↔ 顧問。由 NORA 設計萃取邏輯，CLAUDE（CEO/審核端）收斂範圍
後實作，並經 NORA 第 2 輪複審抓出「會產垃圾內容」的風險後修正。

### 新增：`seo-advisor write --from-report`

把顧問模式找出的 SEO 缺口，一鍵轉成針對性的寫作 brief——「找到問題 → 直接產
內容補洞」，真正把兩個已實作模組串起來。

```bash
seo-advisor audit consultant --url example.com --out ./report
seo-advisor write --from-report ./report/report.json --llm-provider mock
```

萃取邏輯（`writers/report_bridge.py`）刻意保守，避免產出無意義或誤導的內容：

- 只有「內容能解決」的缺口才轉成寫作任務（content_quality / internal_linking），
  且需含內容訊號詞才納入。
- 純技術/資安問題（4xx、canonical 跨網域、noindex、HTTPS、security）一律排除，
  不會被誤轉成文章。
- **批次 metadata 任務不寫長文**：多頁重複 metadata 會要求只產各頁 title/meta/H1
  清單，而非硬寫一篇文章（NORA 複審抓到的核心風險）。
- 內鏈任務要求提供具體錨文字與連結來源，不泛泛說「多加內鏈」。
- 全 P3 的機會標「低優先」、本地掃描相對路徑標「本地路徑」避免誤導。
- 沒有內容缺口且未給 `--topic` 時友善停止，不硬產空 brief。
- 使用者的 `--topic` 永遠優先；`--from-report` 補 source_notes/internal_links/
  intent/target_url。

### 測試 / CI

新增 11 個 report_bridge 測試（含技術問題排除、無機會停止、metadata 不寫長文、
severity 排序等），CI 增加 `write --from-report` 串接 smoke。總計 275 測試全過。

## [0.1.11] - Unreleased

輸出實用度強化。由 NORA 全技能盤點提出優化清單，CLAUDE（CEO/審核端）挑出
「高價值 + 風險可控」批次執行，並經 NORA 第 2 輪複審抓出誤報後修正。

### 新增 SEO 檢查（Consultant Mode，大幅提升診斷實用度）

- **canonical 跨網域檢查**：偵測 canonical 指向不同網域（會把搜尋權重讓給外站）。
  已對 `www.x.com` ↔ `x.com` 等合法 canonicalization 做 host 正規化避免誤報；
  文案提醒轉載/多網域/遷移可能是刻意設定，請確認。
- **Open Graph 檢查**：偵測頁面缺少 og:title / og:image（分享到社群時沒有預覽
  卡片、降低點擊）。已跳過 noindex 頁與 API/後台路徑降噪。
- **JSON-LD 結構化資料檢查**：偵測 JSON-LD 語法無法解析（會失去 rich result）。

### 輸出品質

- Growth 成效分析的低轉換 / 高成本 finding 補上**判斷門檻透明化**
  （flagged_threshold、threshold_rule、roas_threshold），並標明為通用預設值、
  提醒依產業與毛利調整，避免暗示絕對標準。

### 測試

新增 10 個測試（三個新檢查的正/負案例、www↔apex 不誤報、noindex/API 頁降噪），
總計 264 個測試全過，ruff lint 乾淨。

## [0.1.10] - Unreleased

深度技術/資安強化。由 NORA 做程式碼層級深度稽核（資安/效能/健壯性/跨平台），
CLAUDE（CEO/審核端）逐項驗證真偽後修補，並經 NORA 第 2 輪複審抓出修正裡的
不完整處再補齊。

### 安全修正

- **[P0] SSRF redirect 繞過**：`HTTPConnector` 原本 `follow_redirects=True`，
  只在請求前檢查原始 URL，公開網址可經 30x 被導向 private IP 或雲端 metadata
  endpoint（如 `169.254.169.254`）而繞過檢查。改為 `follow_redirects=False`
  + 手動 `_safe_get()`，**每一跳都重新做 SSRF 檢查、只允許 http/https、超過
  上限即停**。已加測試證明 metadata 內容拿不到、file:// 被擋、正常 redirect 仍運作。
- **[P1] 回應大小上限（真串流）**：`_safe_get` 改用 `client.stream()`，body
  邊下載邊累加、超過上限（HTML 10MB / sitemap 20MB）即中止下載，避免超大
  回應把整個 body 讀進記憶體造成 memory DoS（不再是下載完才截斷）。
- **[P1] sitemap index 放大**：傳入剩餘 `limit`、子 sitemap 數上限 50、每次
  子 sitemap 抓取前套 rate limit、達 limit 即停，避免請求放大 / 資源耗盡。
- **[P1] 本地檔案大小上限**：`LocalArchiveConnector` 讀檔前先 `stat()`，超過
  25MB 的檔案回報 `file_too_large` 而不讀進記憶體。
- **XML 安全**：sitemap 解析前拒絕含 `<!DOCTYPE` / `<!ENTITY` 的內容，徹底
  避免 billion laughs / XXE（無需新增 defusedxml 依賴）。
- **錯誤訊息遮蔽**：新增 `redact_secrets`，統一遮蔽 URL 內帳密、`token=`、
  `sk-*` / `sk-ant-*` 金鑰、本機使用者路徑；`FriendlyError.render` 全面套用，
  避免錯誤訊息意外洩漏敏感資訊。

### 健壯性 / 驗證

- `AdsSafetyPolicy` 與 `InsightsRow` 的金額/百分比/次數/天數欄位加
  `Field(ge=0, le=...)`，避免被設成負數或荒謬值而讓預算保護失效。

### 測試

新增 http 資安測試（SSRF redirect、串流截斷、DOCTYPE 拒絕）、redaction 測試、
ads 數值驗證測試，總計 255 個測試全過，ruff lint 乾淨。

## [0.1.9] - Unreleased

新手/傻瓜快速啟用 + 使用者體驗優化。由 NORA 扮演多視角稽核機器人（傻瓜使用者/
新手開發者/資深 UX/無障礙/文案信任）互相審核、來回多輪，CLAUDE（CEO/審核端）
每輪把關收斂。

### 修正

- **[bug]** 裸網域 URL：新手直接打 `example.com`（沒有 `https://`）原本會被
  autopilot 誤判成「模糊目標」而跑錯模組。新增 `url_utils.looks_like_url`，
  現在裸網域會正確當網址跑顧問/CRO/UTM，含空白的自然語言仍走 matrix。
- `auto --approve` 原本會在同意後**重跑一次分析**；改為 `apply_consent` 用
  同一份已預覽並經同意的計畫更新狀態，不重跑（更快、且保證執行的正是你看過的）。

### 使用者體驗 / 新手友善

- **信任文案統一**：README/QUICKSTART/SKILL/wizard 的「全程免費、不會花任何錢」
  全改成「預設只做分析、不花錢、不改動你的網站；付費或寫入動作會先列明細、
  你同意一次才執行」，消除與 approve 機制的語意衝突。
- `auto` 首屏固定印出安心提示（預設不花錢/不發布/不寫入）。
- **誠實標示**：`ModuleResult` 加 `execution_mode`，報告以人話標籤呈現
  （已完成掃描/已完成分析/示範資料/已產生行動計畫），並在每項後附「拿完整
  結果可貼上的指令」，避免讓人以為已做完整掃描、也不會覺得「什麼都沒做」。
- 新增 `cost-estimate.md`（給人看的成本明細），JSON 標明「給自動化用」。
- 完成訊息主推白話懶人包，並附「怎麼打開這個檔案」的可複製指令
  （Windows `start` / macOS `open` / Linux `xdg-open`）。

### 安裝腳本 / 文件

- `install.ps1`：加 Python >= 3.10 版本硬擋；移除會讓人誤以為卡住的 `--quiet`；
  成功訊息改成「複製貼上、免啟動虛擬環境」的完整指令，並附 execution policy
  被擋時的 fallback。
- `install.sh`：移除 `--quiet`；成功訊息同樣改成免 activate 的完整指令。
- `QUICKSTART.md`：加「找不到 seo-advisor 指令」的免 activate fallback。

### CI / 測試

- CI 增加：autopilot 產出 `cost-estimate.md` 檢查、裸網域 `auto example.com`
  正確路由檢查。
- 新增 `looks_like_url`、`apply_consent`、裸網域路由測試。

## [0.1.8] - Unreleased

紮實度強化版：由 NORA 做一次全專案體檢找出弱點，CLAUDE（CEO/審核端）審核後
逐項修補。不加新功能，專注把已有的東西變得更紮實、更誠實、更不會絆倒人。

### 修正

- **[bug]** 修正 `autopilot.runner` 的 `mock=task.mock or True`——這個 `or True`
  讓成本估算永遠是 mock 模式，未來接真實 provider 時會低估成本、失去安全意義。
  改為明確的 `_MVP_FORCE_PLAN_ONLY` 常數，並加回歸測試鎖住「真實模式不得被
  標成 mock」。
- 修正 Windows 透過 pipe/精靈輸入中文會因 surrogate 編碼崩潰的問題
  （`_console_encoding` 也 reconfigure stdin，見 v0.1.7 亦有）。

### 文件

- 新增 `docs/capability-map.md`：一頁能力地圖，標清每個能力
  implemented/mock/plan-only/skeleton，並定義 Core Modes / Marketing Modules /
  Orchestrators 三層 taxonomy。若與其他文件衝突以此為準。
- 新增 `docs/api-contracts.md`：給貢獻者的介面契約速查。
- 修正過時敘述：README tagline 更新為「行銷營運技能」、`docs/modes.md` 標題與
  Content Writer 狀態、QUICKSTART 改成一鍵 auto 流程。
- `CONTRIBUTING.md` 擴充：新增 module/provider 貢獻規範、方法論合規紅線
  checklist、pip/pipx 安裝指南。

### 開發者體驗 / CI

- CLI 頂層 help 改成 taxonomy 導覽（最快上手 + 三層分類 + 完整指令）。
- CI 擴充：所有公開 demo 指令的 smoke test（auto/growth/ecommerce/matrix/
  image/ads/consultant demo）+ `python -m build` 後在乾淨 venv 安裝 wheel 跑
  demo，驗證 package-data 都被打包。
- `pyproject.toml` 加相依主版本上限（避免破壞性大版更新打壞使用者/CI）。
- Growth/Ecommerce 的 heuristic 報告加「自動推測、非人工判定」提醒，避免過度
  肯定的信任問題。

### 測試

新增 12 個測試（autopilot 成本 bug 回歸、11 條 provider 失敗路徑），
總計 240 個測試全過，ruff lint 乾淨。

## [0.1.7] - Unreleased

讓完全的新手/小白用「一個指令、3 分鐘、放著不管」就能拿到專家級優化方案。
由 NORA 設計架構、CLAUDE（CEO/審核端）審核成本估算誠實度與同意流程安全性
後落地。

### 新增：一鍵代操機器人（`seo-advisor auto`）

- `seo-advisor auto <網址或目標>`：一個指令自動判斷該跑哪些模組、跑遍分析、
  產出白話懶人包 + 完整報告 + 成本明細 + 待辦清單。全程免金鑰、不花錢。
- **一次知情同意**：會花錢/寫入/發布的動作先彙整成白話成本明細
  （`CostEstimate`：動作、類別、金額或 token 估算、風險、是否可回滾），
  使用者輸入一次同意確認字串後才執行——單純 `y` 不算同意，避免誤按燒錢。
- **同意 ≠ 無限授權**：安全白名單（本地報告/素材、可回滾低風險動作）才可
  同意後自動執行；黑名單（刪除、付款、發布、改 DNS/伺服器、增加預算超上限、
  不可回滾操作）永遠不自動做。成本估算誠實——無法精確估的標 estimated/unknown。
- MVP：分析全自動免金鑰；真實花錢動作（產圖/產文/廣告調整）一律停在計畫，
  成本明細透明呈現，確保現階段絕不誤燒錢。
- 互動精靈第一個選項改為「一鍵全自動」，最推薦新手使用。

### 修正

- 修正 stdin 編碼問題：Windows 上透過 pipe 或精靈輸入中文（例如中文目標）
  原本會因 surrogate 編碼在寫檔時崩潰；`_console_encoding` 現在也 reconfigure
  stdin 為 UTF-8（errors="replace"），讓所有精靈的中文輸入穩定。

### 測試

新增 15 個 autopilot 測試（含成本明細誠實性、同意閘門確認字串、白名單/黑名單
安全性），總計 229 個測試全過，ruff lint 乾淨。

## [0.1.6] - Unreleased

把業界行銷/電商方法論以**中性化蒸餾**方式納入專案，讓任何人免費就能用這些
方法論自我健檢，不需買課或代操。由 NORA 蒸餾、CLAUDE（CEO/審核端）審核合規
與品質後落地。

### 合規原則（本版核心）

- 方法論一律**中性化蒸餾**：只萃取業界公開、廣泛認可的通用原則，轉成不具名、
  可執行的檢核清單。**不使用任何真實專家人名、課程名或商標**，不逐字複製任何人
  的著作或付費課程，不宣稱與任何專家有關聯或代言。與 content_writer_guide.md
  的合規精神一致。
- 新增自動化測試 `test_methodology_is_neutralized_no_expert_names`，讓 CI 持續
  守護這條紅線。

### 新增：行銷方法論知識庫（`knowledge/methodology.yaml`）

- 四大領域共 50 條可執行檢核原則：電商 listing 優化（12）、付費廣告漏斗（12）、
  內容品牌成長（12）、轉換/成長駭客（14）。
- `knowledge` 載入器用 importlib.resources 讀取，供各模組引用。

### 新增：電商 Listing 健檢模式（`seo-advisor ecommerce`）

- 運用電商方法論原則檢核 listing 的標題、賣點、主圖/副圖、A+、後端關鍵字、
  評論/評分、庫存與購買入口、變體，產出健康分數與建議。
- 缺貨（P0）、缺 Buy Box/低評分/缺主圖（P1）等直接影響轉換的問題優先分級。
- 每個發現都引用對應的方法論檢核點；資訊不足的欄位不硬給 finding。
- 純邏輯免金鑰：`seo-advisor ecommerce audit/demo`。

### 測試

新增 22 個測試（ecommerce 8、knowledge 4、含合規測試，及 router/wheel 擴充），
總計 214 個測試全過，ruff lint 乾淨。

## [0.1.5] - Unreleased

本版由 NORA 先稽核「成熟網路行銷團隊該有、但專案還缺」的能力缺口，CLAUDE
（CEO/審核端）審核後派工、NORA 執行、CLAUDE 落地。補齊網路行銷完整能力鏈。

### 新增：成長行銷模組（Growth Marketing，`seo-advisor growth`）

- **UTM 歸因規劃**（`growth utm`）：一致命名的 tagged URL 產生器、命名規範
  建議、歸因衛生檢查（缺必要欄位/大小寫混用/中文空格/跨渠道 campaign 重用）。
  純邏輯，免金鑰。
- **CRO 落地頁優化**（`growth cro`）：六類轉換率診斷（結構/CTA/表單/信任訊號/
  訊息一致性/速度提示）+ A/B 測試設計（假設/對照版/實驗版/主要指標/樣本量）。
  有 URL 時透過 HTTPConnector read-only 抓頁面，抓不到退回通用規劃。
- **跨渠道成效分析**（`growth analytics`）：`AnalyticsProvider` 抽象層
  （GA4/Search Console/Google Ads read-only + Mock），四類診斷（追蹤缺漏/
  高流量低轉換/高成本低回報/擴量機會），用中位數轉換率做動態門檻。
  一律 read-only——即使 Google Ads 也只讀成效、絕不改預算。無憑證時用 mock。

### 擴充：矩陣角色行銷能力

- 補上路由關鍵字與 mock 行動：Email/EDM（MIRA）、競品分析與市場調研（ATLAS）、
  跨平台內容行事曆與影音腳本（MAYA）、口碑評論管理（TARA）、聯盟行銷（REX）、
  再行銷（JACK）。

### 安全

- Google 成效 API 一律 read-only；Email 只規劃不寄送；廣告預算變更仍走
  既有 dry-run 計畫流程。

### 測試

新增 39 個測試（growth 18、matrix 路由擴充等），總計 200 個測試全過，
ruff lint 乾淨。

## [0.1.4] - Unreleased

新增「AI 矩陣營運系統」作為七大模式之上的統籌層。本版由 CLAUDE（升為
最高執行長／審核端）派工、NORA（原 CODEX 工作機器人更名，擔任總控長／
工程執行端）執行，CLAUDE 審核後落地——協作規則記錄於 `.collab-rules.md`。

### 新增：AI 矩陣營運系統（AI Matrix Operating System）

- `matrix/` 模組：把 AI 從單一工具升級為可跨行業套用的虛擬組織。
- 26 個 AI 工作夥伴角色，**資料驅動**（`assets/roles.yaml`，不為每個角色
  寫 class），涵蓋總控/策略/行銷/銷售/產品/營運/財務/人資/法務/行政。
- NORA 路由器（`router.py`）：依 user_goal 關鍵字 + 行業加權選角色，
  對應規劃書的四個範例情境（製造業新品/餐飲來客/課程招生/內部流程）。
- **安全升級規則**：任何含 write/deploy/spend/publish/send（中英文）的任務，
  即使角色平常不需審核，也強制升級為 human_review_required + plan-only。
  JACK（廣告預算）/ LEX（法務）/ GRACE（財務）/ ECHO（發布）在 roles.yaml
  預設就標記需人工審核。
- engine 抽象層：MockEngine（免金鑰）、GenericLLMEngine（接 Content Writer
  的 LLMProvider，無金鑰時 fallback 到 mock）。Phase 2 會把 IRIS/MAYA/JACK/
  PIXEL 接到對應專屬引擎。
- planner（派工）+ synthesizer（整合成 MatrixDeliverable）+ runner。
- CLI：`seo-advisor matrix run / demo / roles / role`。
- 角色卡與 prompt 用 importlib.resources 打包（wheel 驗證測試已擴充）。
- 新增 16 個 matrix 測試，總計 179 個測試全過。

## [0.1.3] - Unreleased

與 CODEX（顧問端）協作開出規格後，新增兩個新的專家模式，讓技能從
「SEO 健檢/內容」延伸到「廣告優化/素材製作」。

### 新增：Meta 廣告優化專家（Meta Ads Mode）

- `AdsProvider` 抽象層（`ads/providers/`）：`MetaAdsProvider`（Meta
  Marketing API，read-only audit）、`MockAdsProvider`（免金鑰試玩）。
- `AdsSafetyPolicy`（`ads/models.py`）：動用真實預算的多重防護。
  **預設值刻意保守**——增加預算、啟用投放、暫停整個活動一律預設禁止，
  需逐項明確開啟；預算變更有百分比/金額/總增額多重上限；帳戶白名單；
  資料量不足時不建議動作。
- 廣告成效診斷（`ads/analyzer.py`）：缺 Pixel（P0）、高花費低 ROAS、
  素材疲勞、擴量候選、資料量不足判斷。
- dry-run 行動計畫（`ads/planner.py`）：只把「不擴大花費」的安全動作
  （暫停低效素材）排入計畫，每個動作都有 rollback snapshot；擴量建議
  只在報告呈現，不自動排入計畫。
- CLI：`seo-advisor ads audit / plan / demo`。實際代操（`apply`）刻意
  尚未開放，整體流程為 audit → plan（dry-run）→ 人工檢視 → 手動套用。

### 新增：GPT 產圖素材專家（Image Material Mode）

- `ImageProvider` 抽象層（`images/providers/`）：`OpenAIImageProvider`
  （gpt-image-1）、`MockImageProvider`（產生佔位 PNG，免金鑰試玩）。
- 合規前置檢查（`images/compliance.py`）：在送出 API 請求前攔截冒用品牌/
  名人肖像、誤導性療效獲利保證、偽造介面、仿冒藝術家風格等違規需求。
- 多用途/多版位/多變體生成，輸出 image-manifest.json 與 AI 生成揭露建議。
- 與 Content Writer 串接：`seo-advisor image from-content` 讀取文章報告
  產生配圖。
- CLI：`seo-advisor image generate / demo / from-content`。

### 其他

- `Mode` enum 新增 `META_ADS` / `IMAGE_MATERIAL`，router 加入對應別名。
- 新增測試 41 個（image 12、ads 17、其餘涵蓋 provider/合規/安全防護），
  總計 163 個測試全過。
- pyproject 新增 optional dependencies：`image-openai`、`ads-meta`。

## [0.1.2] - Unreleased

本版本源自與 CODEX（審核端）協作的全面架構/資安/新手體驗稽核，修正
稽核發現的問題，並完整實作 Content Writer Mode。

### 安全性修正

- **[P0]** 修正 `LocalArchiveConnector` 解壓 zip 檔案時的 zip slip /
  path traversal 漏洞（新增 `security/safe_archive.py`：
  `safe_extract_zip()` 逐項驗證解壓路徑，`resolve_inside_root()` 約束
  所有檔案存取在掃描根目錄內），並加上 zip bomb 防護（檔案數量／單檔／
  總解壓大小上限）。
- 新增 `SafetyPolicy`（`models.py`）：把 `docs/connector_contract.md`
  定義的資安原則（dry-run、capabilities、SSRF 防護）從文件變成建構子
  強制要求的參數，所有 Connector 都需接受並遵守。
- `HTTPConnector` 補上：robots.txt 遵循（`security/robots_policy.py`）、
  請求速率限制（`security/rate_limiter.py`）、SSRF 基本防護
  （`security/network_policy.py`，拒絕 localhost/私有網段/雲端 metadata
  IP）、sitemap 爬取範圍限制（不會照單全收爬取外部網域的 URL）、
  redirect 導致的 host 變更會正確更新允許爬取範圍。
- URL 正規化拒絕含帳號密碼的網址（例如 `https://user:pass@example.com`），
  避免憑證意外外洩到報告或日誌。

### 修正

- 修正 `WebsiteConnector.fetch_url()` 抽象簽名與實際呼叫不一致的問題。
- 修正 duplicate title 檢查的 evidence 錯誤：原本 `affected_urls` 沒有
  真的過濾出重複標題的頁面，而是回傳前 20 個任意頁面。
- 修正 demo 模式與 scoring 設定的打包問題：原本讀取
  `scripts/tests/fixtures/`、`config/scoring.yaml`，這些路徑在正式
  wheel 安裝後不存在；改用套件內建資產（`demo_assets/`、
  `config_assets/`）+ `importlib.resources`，並新增
  `test_wheel_packaging.py` 用實際建置 wheel 驗證。
- `scan_runner.py` 新增 preflight 連線檢查：網站完全連不上（DNS/連線/
  逾時失敗）時拋出清楚錯誤，不再產出一份空洞卻顯示「掃描完成」的報告。

### 新增

- **Content Writer Mode 完整實作**（`scripts/seo_advisor/writers/`）：
  - `LLMProvider` 抽象層：`AnthropicProvider`、`OpenAIProvider`、
    `LocalProvider`（Ollama，免費）、`MockProvider`（測試/離線試玩用）。
  - brief → outline → draft → QA 四階段流程（`pipeline.py`）。
  - 程式化品質檢查（`quality.py`）：單一 H1、低品質 AI 內容起手式、
    YMYL 關鍵字偵測，併入 LLM QA 結果。
  - CLI 指令 `seo-advisor write`，支援 `--llm-provider mock` 免 API
    金鑰試玩。
- 新增 noindex / X-Robots-Tag 檢查（`analyzers/technical.py`）。
- 新增本地 HTML 編碼偵測（`encoding_utils.py`），支援 Big5/Shift_JIS/
  GBK 等非 UTF-8 網站，避免中日韓文字被誤判為缺少內容。
- `scoring.py` 讀取 `config/scoring.yaml` 的 `category_weights`，
  計算加權後的網站健康分數。
- 白話報告加上「已檢查範圍內」措辭與具體問題（sitemap/canonical/
  noindex 等）的白話說明對照表。
- CI 新增跨平台測試矩陣驗證 wheel 打包正確性。

## [0.1.1] - Unreleased

### Added（新手體驗優化）

- `QUICKSTART.md`：5 分鐘上手指南，不要求先懂 Python 或 SEO。
- `install.ps1` / `install.sh`：一鍵安裝腳本，自動偵測 Python、建立
  虛擬環境、安裝套件並驗證安裝結果。
- `docs/install-troubleshooting.md`：常見安裝問題排解。
- `docs/glossary-for-beginners.md`：SEO 術語白話對照表（sitemap、
  canonical、robots.txt 等，用生活化比喻解釋）。
- CLI 互動精靈（`seo-advisor` / `seo-advisor start`）：不帶參數執行時
  用問答方式引導完成掃描，不需要記任何指令參數。
- `seo-advisor demo`：不需要輸入任何網址，直接用內建範例資料產生
  完整報告，方便新手在掃描自己的網站前先了解報告長相。
- URL 自動正規化（`url_utils.py`）：使用者輸入 `example.com` 會自動補上
  `https://`，不再要求手動輸入完整網址格式。
- 人話錯誤訊息（`errors.py`）：連線逾時、網址錯誤、檔案不存在等常見
  錯誤，預設顯示可理解的說明與下一步建議，而非 Python traceback；
  加上 `--debug` 才顯示完整技術細節。
- 白話文報告層（`beginner_report.py` → `report-beginner.md`）：用「房屋
  健檢」比喻解釋網站健康分數與 P0-P3 優先順序，附上「最該先處理的
  3 件事」，供非技術人員（老闆、客戶）閱讀。
- CLI 進度提示：掃描過程顯示「第 X/4 步」階段性文字，讓使用者知道
  工具正在運作而非卡住。
- 報告輸出改為固定檔名（`report-beginner.md` / `report.md` /
  `report.json`），不再使用隨機 ID 檔名，方便新手直接找到檔案。
- 修正孤兒頁（orphan page）誤判：單頁網站的唯一頁面不再被誤判為孤兒頁。

## [0.1.0] - Unreleased

### Added

- 專案骨架、SKILL.md、文件（architecture / modes / connector contract /
  content writer guide / i18n guide / roadmap）。
- Finding / Report / Connector 的 JSON Schema。
- `WebsiteConnector` 抽象介面，實作 `HTTPConnector`、`LocalArchiveConnector`。
- 顧問模式（Consultant Mode）核心：技術面 crawler（robots.txt / sitemap /
  canonical / title・meta・H1 / 內外連結 / 狀態碼）、scoring、
  Markdown + JSON 報告產出。
- CLI 入口（`seo_advisor.cli`）與五大模式路由骨架（工程師／資安／文章寫手／
  外掛開發模式先提供 prompt 模板與介面，執行邏輯留待後續版本）。
- 基本測試與範例設定。

### 尚未實作（規劃於後續版本，見 `docs/roadmap.md`）

- Engineer Mode 的自動修復（fixers）。
- Security Mode 的主動掃描邏輯。
- Content Writer Mode 的 LLM 呼叫整合。
- Plugin Dev Mode 的 WordPress 外掛 scaffold。
- SSH / Git / WordPress API / Cloudflare / cPanel connector。
