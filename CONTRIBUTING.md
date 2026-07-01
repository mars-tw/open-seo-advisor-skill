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

## 貢獻新的 Connector

所有 Connector 必須：

1. 繼承 `seo_advisor.connectors.base.WebsiteConnector`。
2. 明確宣告 `capabilities()`（例如 `read_files`、`write_files`、
   `run_commands`、`deploy`）。
3. 預設所有寫入類操作走 `dry_run=True`。
4. 不得在例外訊息、log 或回傳值中包含憑證原文。
5. 附上對應的 `scripts/tests/` 測試（可用假資料 / mock，不需要真實外部主機）。

詳見 `docs/connector_contract.md`。

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
