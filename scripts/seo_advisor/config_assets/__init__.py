"""隨套件一起打包的預設設定檔（config/*.yaml 的複本）。

背景：專案根目錄的 config/ 資料夾方便開發者直接檢視與修改，但它不在
`seo_advisor` 套件範圍內，正式打包成 wheel 安裝後不會存在（與 demo_assets
遇到的打包問題相同）。因此把 Consultant Mode 執行期需要讀取的預設設定，
複製一份放在這裡，透過 importlib.resources 存取，確保任何安裝方式下
都能正確載入預設值。

若使用者想要客製化評分權重，可用 CLI 的 --scoring-config 指定外部 YAML
路徑覆寫（見 scoring.py 的 load_scoring_config()）。維護時，這裡的內容
應與 config_assets/scoring.yaml 所複製的 config/scoring.yaml 保持一致。
"""
