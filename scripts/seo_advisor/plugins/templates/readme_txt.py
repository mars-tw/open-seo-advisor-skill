"""`readme.txt` 的模板（WordPress.org plugin readme 標準格式）。"""

from __future__ import annotations

from seo_advisor.plugins.models import PluginScaffoldRequest


def render_readme_txt(req: PluginScaffoldRequest) -> str:
    return f'''=== {req.plugin_name} ===
Contributors: {req.author}
Tags: seo, schema, structured-data, json-ld
Requires at least: 5.8
Tested up to: 6.6
Requires PHP: 7.4
Stable tag: {req.version}
License: {req.license}

{req.description}

== Description ==

{req.plugin_name} 在前台輸出 Organization/WebSite/Article 的 JSON-LD
結構化資料，設定值透過「設定」選單下的頁面管理。

這份 scaffold 由 Open SEO Advisor 產生，請先在 staging/測試站台安裝並
完整測試，自行審閱程式碼、依你的站台需求調整，確認無誤後才部署到正式
環境。

== Installation ==

1. 上傳外掛資料夾到 `/wp-content/plugins/` 目錄，或透過 WordPress 後台
   「安裝外掛」上傳這個 zip 檔案。
2. 在「外掛」選單啟用 {req.plugin_name}。
3. 到「設定」→「{req.plugin_name}」填入公司/組織資訊。

== Changelog ==

= {req.version} =
* 初始版本（由 Open SEO Advisor scaffold 產生器產生）。
'''
