"""CI 保險機制：鎖住「_MVP_FORCE_PLAN_ONLY 與白名單/黑名單複核」這兩者的一致性。

背景（全系統健康度辯論發現）：autopilot/safety.py 定義了完整的
is_auto_executable() 白名單/黑名單複核邏輯，但 autopilot/runner.py 的
_execute_safe_actions() 目前完全沒有呼叫它，只是把所有花錢/寫入動作硬編碼
標成 plan_only，靠 _MVP_FORCE_PLAN_ONLY = True 這個常數兜底。

現階段這不構成漏洞（常數恆為 True，什麼都不會真的自動執行），但這代表「同意
閘門後的白名單/黑名單複核」完全沒有被真實執行路徑覆蓋——這是一種容易在版本
演進中被遺忘的「看似有防護、實則未接線」風險：一旦未來有人把
_MVP_FORCE_PLAN_ONLY 改成 False 以開放真實代操，卻忘記同時把
_execute_safe_actions 接上 is_auto_executable 複核，那麼「已經設計好的安全
機制」在那個時間點就會是空的。

這條測試不試圖「現在就接線」（仲裁裁決：現在做無實益），而是當一種機制性
提醒：只要 _MVP_FORCE_PLAN_ONLY 還是 True，測試就通過；一旦有人把它改成
False，測試會立刻失敗並提示「請同時讓 _execute_safe_actions 呼叫
is_auto_executable 複核，否則白名單/黑名單形同虛設」。
"""

import inspect

import seo_advisor.autopilot.runner as runner_module


def test_force_plan_only_must_stay_true_until_executor_checks_allowlist():
    is_wired_up = "is_auto_executable" in inspect.getsource(runner_module._execute_safe_actions)

    if not is_wired_up:
        assert runner_module._MVP_FORCE_PLAN_ONLY is True, (
            "偵測到 _MVP_FORCE_PLAN_ONLY 已被改為 False，但 "
            "_execute_safe_actions() 尚未呼叫 autopilot.safety.is_auto_executable() "
            "做白名單/黑名單複核。開放真實自動執行前，請先讓 executor 對每個要"
            "執行的動作呼叫 is_auto_executable() 做二次確認，否則同意閘門後的"
            "安全防護形同虛設。"
        )
