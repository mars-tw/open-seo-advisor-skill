"""IndexNow 發布整合：內容更新後主動通知 Bing/Yandex 等支援 IndexNow
協定的搜尋引擎，加速重新抓取。

獨立 CLI 指令（`seo-advisor indexnow ...`），不自動接掛在 Engineer Mode
之後——IndexNow 是「對外發布通知」，貿然在 fixer 套用後自動觸發容易在
dry-run/測試環境誤送，這輪由使用者自行決定何時執行。
"""
