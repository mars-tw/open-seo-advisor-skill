"""Plugin Dev Mode 的 CMS 外掛 scaffold 產生器。

v0.3.5 起支援 WordPress `schema-generator`（Organization/WebSite/Article
JSON-LD 產生器）。`indexnow-notifier`/`internal-linking` 留待後續版本
（見 ../../docs/roadmap.md）。CLI 見 `cli.py`；規格見
../../docs/modes.md 的 Plugin Dev Mode 一節。

純本機檔案產出，不做任何遠端安裝/部署——只在 `--out` 指定的目錄下產生
可審閱的 PHP scaffold 與（可選的）zip 打包。
"""
