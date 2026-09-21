# 使用 OpenCode 建立 SEO／AEO 網站

查核日期：2026-09-21。[OpenCode 繁中首頁](https://opencode.ai/zht)提供終端機、桌面與編輯器入口。
本指南讓 OpenCode 載入同一套 `open-seo-advisor`，沿用兩個公開範例的敘事方法、GPT 素材流程與部署指南。
OpenCode 與 `seo-advisor` 是不同工具：前者是執行技能的 agent，後者是本專案的 Python CLI。

## 1. 安裝 OpenCode

依 [OpenCode 官方安裝文件](https://opencode.ai/docs/)選擇適合環境的方式。已有 Node.js／npm 時可用：

```bash
npm install -g opencode-ai
opencode --version
```

Windows 可用官方列出的 npm、Scoop 或 Chocolatey；官方建議 WSL，但本技能不要求為了安裝而新增 WSL。
使用 WSL 時，OpenCode、技能、Python 與專案都放在同一個 Linux 環境，勿把 Windows 的 `.venv` 搬進去執行。
[Windows 說明](https://opencode.ai/docs/windows-wsl/)

## 2. 把技能放到網站專案

在準備建立或修改的網站專案根目錄執行：

```bash
git clone https://github.com/mars-tw/open-seo-advisor-skill.git .opencode/skills/open-seo-advisor
```

這會建立一個獨立的技能 Git 副本，方便另外更新；若外層網站也使用 Git，不要把它當一般資料夾
直接加入版控，以免成為缺少設定的 gitlink。需要讓技能跟網站一起版控時，使用下一段的 ZIP 方式：
放入不含 `.git` 的檔案副本。副本更新時重新比對並替換，不能直接在其中執行 `git pull`。

也可下載本專案 ZIP，將解壓後的完整內容放進下列目錄。不要只搬 `SKILL.md`，需要保留 `docs/`、
`scripts/`、`examples/` 及其他相對引用。若目的地已有技能，先比較版本與修改，不直接覆蓋。

```text
你的網站專案/
└── .opencode/
    └── skills/
        └── open-seo-advisor/
            ├── SKILL.md
            ├── docs/
            ├── scripts/
            ├── examples/
            └── integrations/
```

全域安裝可改放 `~/.config/opencode/skills/open-seo-advisor/`，這裡的 `~` 是執行 OpenCode 的
使用者家目錄；自訂設定路徑時依該環境配置。不要假設 Codex 的 `~/.codex/skills` 會被 OpenCode 自動發現。
同一環境避免安裝多份同名技能，除非你確實要用專案版覆蓋全域版。[技能發現規則](https://opencode.ai/docs/skills/)

## 3. 選模型並開始建站

從網站專案根目錄啟動，而非從技能資料夾啟動：

```bash
opencode
```

尚未連接模型時，依 OpenCode 介面的 `/connect` 完成服務商設定，再用 `/models` 選擇可用模型。
保留已有帳號、模型與權限配置，不必為這個技能建立全新的設定檔。模型服務、GPT 產圖與網站託管
各自有額度或費用，不因 OpenCode 開源就全部免費。[模型服務設定](https://opencode.ai/docs/providers/)

在允許寫入檔案的 **Build** 模式輸入：

> 請載入 open-seo-advisor 技能，帶我建立一個工筆神明畫像的 SEO／AEO 網站。我要看見畫稿、勾線、設色到完成的捲動故事，圖片使用 GPT 生成，主機優先 Cloudflare 免費方案。先確認品牌與神明主題，再完成可預覽網站。

也可以改成商品銷售、購物或互動體驗。若停留在 Plan 模式，只會規劃；準備實作時切到 Build。
`/init` 會建立專案指引，並不是安裝技能的必要步驟；已有 `AGENTS.md` 時保留原規則。
[Plan／Build 使用方式](https://opencode.ai/docs/)

OpenCode 應實際透過 `skill` 工具載入 `open-seo-advisor`，再依技能基底目錄讀取建站文件。
相對的參考、模板與腳本路徑以技能資料夾為準，網站輸出放在目前網站專案中，不能寫回技能範例當成新案。

## 4. 可選的一行建站指令

本專案附 [seo-website.md](../integrations/opencode/seo-website.md)。將它複製為網站專案內的：

```text
.opencode/commands/seo-website.md
```

也可放到 `~/.config/opencode/commands/seo-website.md` 作全域指令；已有同名檔時先比較，不覆蓋。
重新開啟 OpenCode 後，在指令選單確認 `seo-website`，即可使用：

```text
/seo-website 工筆媽祖畫像，五段作畫動畫，GPT 圖片，Cloudflare 免費主機
```

`$ARGUMENTS` 會帶入你的需求。這個檔案不指定模型、不放寬權限、不執行內嵌 shell，也不要求切換 agent；
請在 Build 模式使用。尚未複製指令檔時直接用上一節的自然語言即可，`/seo-website` 不會憑空註冊。
[OpenCode 自訂指令](https://opencode.ai/docs/commands/)

## GPT 圖片與部署

先檢查 OpenCode 當前實際可呼叫的產圖 MCP 或自訂工具，確認回傳圖片檔案並打開驗收。
OpenAI／ChatGPT 模型連線、圖片附件或「能看圖片」都不等於能生成圖片，不能假設有 Codex 的內建 `image_gen`。
沒有產圖工具時，繼續完成文案、分鏡、圖像提示詞與程式，並讓使用者選擇提供 ChatGPT 生成圖，或明確選用
已設定的 OpenAI 圖像 API。素材完成前要標示待補，不能用 CSS 佔位宣稱 GPT 圖片已完成。
詳見 [GPT 素材流程](website-assets.md) 與 [OpenCode 工具說明](https://opencode.ai/docs/tools/)。

網站部署依 [託管指南](website-hosting.md)與使用者已授權的平台進行；這套指令不會替你開帳務、
寄送資料或收款。用「畫布離開動畫段落後不再遮住頁尾」等實際畫面驗收，不只確認程式沒有報錯。

## Python CLI 是選用工具

使用 agent 建站不需要先安裝整套 Python CLI。要用離線精靈或稽核功能時，再在網站根目錄執行：

```bash
python -m pip install -e ./.opencode/skills/open-seo-advisor/scripts
seo-advisor website init --out ./my-site
```

Python 需 3.10 以上；Linux／WSL 若系統限制 pip，先依環境建立虛擬環境。CLI 只產生離線骨架與檢查結果，
仍需 agent 接上真素材、功能與部署。

## 找不到技能或指令時

確認資料夾叫 `open-seo-advisor`、檔名是大寫 `SKILL.md`，沒有 ZIP 多包一層目錄，並在正確的網站專案開啟
OpenCode。檢查 skill 是否被 `deny`、`skill` 工具是否關閉，以及實際載入的是專案版還是舊全域版。
不為排錯把所有權限設成 `allow`。

本套檔案使用 V1／V2 都可辨識的目錄形式與保守 frontmatter。V1 的 skill 工具使用 `name`，V2 使用 `id`；
由 agent 依當前工具 schema 呼叫，不在指令模板硬寫工具參數。兩版權限設定格式不同，改設定前應查對應版本。
[V2 技能](https://opencode.ai/v2/docs/skills/)／[遷移說明](https://opencode.ai/v2/docs/migrate-v1)

## 本專案的實測範圍

2026-09-21 使用 OpenCode **1.18.31**，在隔離的網站專案放入完整技能與 command 檔，執行
`opencode debug skill --pure` 及 `opencode debug config --pure`。已確認載入的是專案內
`open-seo-advisor/SKILL.md` 的內容，所需文件／模板存在，且 `/seo-website` 模板被辨識、`$ARGUMENTS` 保留。
這是技能發現與指令解析驗證，未登入模型服務、未呼叫 LLM 或產圖 API；V2 部分依官方文件核對，未宣稱實跑。
