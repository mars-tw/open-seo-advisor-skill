# 貢獻指南

感謝你願意為 Open SEO Advisor 貢獻！這是一個開源給全球任何人使用與修改的專案，
歡迎任何形式的貢獻：新的 connector、analyzer、fixer、產業設定檔、語言在地化、
文件修正、bug 回報。

## 開發環境設定

```bash
git clone https://github.com/<your-username>/open-seo-advisor-skill.git
cd open-seo-advisor-skill/scripts
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

> 一般使用者（非開發者）未來套件發布到 PyPI 後，可用
> `pipx install open-seo-advisor` 或 `pip install open-seo-advisor` 直接安裝
> CLI，不需要 clone 原始碼。目前請用上述 editable install。

## 貢獻新的 Connector

所有 Connector 必須：

1. 繼承 `seo_advisor.connectors.base.WebsiteConnector`。
2. 明確宣告 `capabilities()`（例如 `read_files`、`write_files`、
   `run_commands`、`deploy`）。
3. 預設所有寫入類操作走 `dry_run=True`。
4. 不得在例外訊息、log 或回傳值中包含憑證原文。
5. 附上對應的 `scripts/tests/` 測試（可用假資料 / mock，不需要真實外部主機）。

詳見 `docs/connector_contract.md`。

## 貢獻新的模組 / provider / engine

專案的介面契約（各 provider 抽象層、報告輸出慣例、資料驅動資產、新增模式的
最小清單）都整理在 **`docs/api-contracts.md`**，動手前請先看。

新增 **provider**（LLM / Image / Ads / Analytics）時務必：

1. 繼承對應的 base 介面，加進 `factory.py`。
2. 金鑰只從環境變數讀取；缺金鑰/缺 SDK 都要拋出帶「請設定/安裝 X」的清楚錯誤。
3. 例外訊息不得包含金鑰/token 原文。
4. 附「缺金鑰」與「工廠未知名稱」兩條失敗路徑測試（見 `tests/test_provider_failures.py`）。

新增 **模式/模組** 時務必附上 `demo` 子指令（免金鑰可跑）、更新
`docs/capability-map.md`、並在 CI 加一條 demo smoke test。

## 貢獻方法論知識庫（合規紅線）

`knowledge/methodology.yaml` 是**中性化蒸餾**的成果。新增或修改原則時：

- ✅ 只萃取業界公開、廣泛認可的**通用**方法論原則。
- ❌ **不得**加入任何真實專家人名、課程名、商標，不得逐字複製他人著作/付費
  課程，不得宣稱與某位專家有關聯或代言。
- 有一條自動化測試（`tests/test_knowledge.py` 的
  `test_methodology_is_neutralized_no_expert_names`）會擋下具名內容——別想繞過它。

反例（不可接受）：「依 XXX 老師的方法…」、建立叫某真人名字的角色/引擎。
正確做法：把方法蒸餾成「檢核點 + 為什麼/怎麼做」的通用原則。

## 貢獻新的產業設定檔或語言在地化

編輯 `config/industry_profiles.yaml` 或 `config/locale_profiles.yaml`，
並在 PR 描述中說明依據的產業慣例或在地化來源。

## 程式碼風格

- Python 3.10+，使用 type hints。
- 用 `ruff` 做 lint、`black` 做格式化（設定見 `pyproject.toml`）。
- 新功能請附測試；修 bug 請附能重現問題的測試。

## Commit 與 PR

- Commit message 請說明「為什麼」而不只是「做了什麼」。
- 一個 PR 聚焦一件事，避免大雜燴 PR。
- 涉及安全性行為（例如新增寫入權限、新增外部 API 呼叫）的 PR，請在描述中
  明確說明資安考量，方便 review。

## 回報安全性問題

請勿在公開 issue 中揭露未修補的安全漏洞，見 `SECURITY.md`。
