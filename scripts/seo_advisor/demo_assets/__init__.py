"""Demo 模式使用的內建示範網站資產。

這些 HTML 檔案透過 importlib.resources 存取（見 ../demo.py），必須確保
scripts/pyproject.toml 有把這個目錄設為 package data，否則正式打包後
使用者安裝的 wheel 會缺少這些檔案，導致 `seo-advisor demo` 失效。
"""
