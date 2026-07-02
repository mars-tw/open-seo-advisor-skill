"""GPT 產圖素材專家（Image Material Mode）。

為廣告、社群、文章、落地頁產生圖像素材。ImageProvider 抽象層可切換
OpenAI / Mock / 未來的供應商。合規前置檢查（compliance.py）會在送出任何
API 請求前攔截違規需求。規格見 ../../docs/image_material_mode.md。
"""
