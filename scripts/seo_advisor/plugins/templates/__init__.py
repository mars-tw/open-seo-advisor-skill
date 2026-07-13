"""WordPress 外掛 scaffold 的 PHP/文字檔案模板。

每個模板都是純函式：接受 `PluginScaffoldRequest`，回傳完整檔案內容字串。
不使用 Jinja2 之類的樣板引擎——模板數量有限，f-string 已經足夠清楚，
且避免多引入一個依賴（見專案既有的精簡依賴慣例）。所有插入模板的值
（slug/plugin_name/author 等）都先經過 `models.py` 的驗證，不會是任意
使用者輸入直接進 PHP 原始碼。
"""
