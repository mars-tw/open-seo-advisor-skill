"""Security Mode：被動式、非破壞性的資安風險掃描，只做觀察不做攻擊性測試。

模組：
- models.py：SecurityFinding/SecuritySeverity/SeoImpact/SecurityReport 資料模型。
- probes.py：暴露檔案偵測、目錄列表偵測（用 HTTPConnector.probe_path()）。
- cloaking.py：一般 UA 與 Googlebot/行動裝置 UA 的內容差異比較。
- https_check.py：憑證/HSTS/mixed content 檢查。
- cms.py：CMS 指紋與版本新舊粗略提示（不查真實 CVE）。
- spam.py：隱藏文字/連結等 SEO spam 跡象。
- runner.py：run_security_audit() 執行入口與授權確認閘門。
- report.py：Markdown/JSON 報告產出。
- cli.py：`seo-advisor security audit`。

安全前提（優先於功能）：只能對使用者明確授權的網站執行；暴露檔案探測與
目錄列表這類「偵查性」檢查，預設需要使用者輸入 `AUDIT <host>` 明確確認
才會執行，`--passive-only` 可跳過確認但只做完全被動的檢查（HTTPS/spam/
cloaking 比較，不探測任何路徑）。
"""
