"""Engineer Mode 的自動修復邏輯：把 Finding 轉成可審核的 PatchPlan，經使用者
確認後才真的寫入檔案。規格見 ../../docs/modes.md 的 Engineer Mode 一節。

模組：
- models.py：PatchPlan/FixTarget/FixResult/RollbackResult 資料模型與寫入白名單。
- safety.py：套用/回滾的確認字串機制。
- robots.py / sitemap.py / canonical.py：各修復類型的 plan_fix()。
- runner.py：Finding → PatchPlan → apply_plan() 的執行入口。
- rollback.py：從備份還原，含「使用者事後又改過就跳過」的安全判斷。
"""
