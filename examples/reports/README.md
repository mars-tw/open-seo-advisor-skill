# 範例報告

- `good-site-example.md` / `.json`：對一個結構良好的測試網站
  （`scripts/tests/fixtures/good_site`）執行 Consultant Mode 的輸出，
  健康分數 96.0/100，僅缺少 robots.txt/sitemap.xml。
- `problematic-site-example.md` / `.json`：對一個刻意製造多項問題的
  測試網站（`scripts/tests/fixtures/bad_site`）執行 Consultant Mode
  的輸出，健康分數 72.5/100，涵蓋缺少 title/H1/meta description、
  canonical 衝突等常見技術 SEO 問題。

這兩份範例可用來快速了解報告的完整結構（Executive Summary、
Site Health Score、Top Findings、依優先順序分組的完整清單）。
