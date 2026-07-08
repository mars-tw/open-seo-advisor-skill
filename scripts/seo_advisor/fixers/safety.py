"""Engineer Mode 的二次確認機制：比 autopilot 的同意閘門更嚴格。

autopilot 的確認字串（見 autopilot/safety.py）只需要「同一句固定格式的話」，
因為那裡同意的是「執行一個已知安全的動作類型」。Engineer Mode 不同：這裡
同意的是「真的把某個檔案改寫掉」，屬於本機檔案系統的直接變更，比花錢動作
更不可逆（花錢動作是財務可回復的，寫壞一個檔案若備份機制有漏洞就真的丟了）。

因此這裡的確認字串必須綁定 plan_id：即使使用者記得「APPLY」這個字，也不能
不小心把它套用到另一個他沒仔細看過的 PatchPlan 上——每次套用都需要重新看過
plan_id（在 dry-run 輸出裡看到），逼迫使用者至少確認「我要套用的是這一份」。
"""

from __future__ import annotations


def build_apply_confirmation(plan_id: str) -> str:
    """產生套用某份 PatchPlan 所需輸入的確認字串。"""
    return f"APPLY {plan_id}"


def build_rollback_confirmation(backup_id: str) -> str:
    """產生還原某份備份所需輸入的確認字串。"""
    return f"ROLLBACK {backup_id}"


def verify_confirmation(user_input: str, expected_phrase: str) -> bool:
    """驗證使用者輸入是否與預期確認字串完全一致（去頭尾空白、不分大小寫）。"""
    return user_input.strip().upper() == expected_phrase.strip().upper()
