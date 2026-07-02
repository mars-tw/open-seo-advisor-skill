"""autopilot 的安全邊界：同意後可自動執行的白名單、永遠不自動做的黑名單，
以及一次知情同意的確認字串驗證。

核心原則：同意不是無限授權——即使使用者同意了，也只執行「已列在成本明細、
已估風險、且在白名單內」的動作；破壞性、不可回滾、付款、對外發布等一律
永遠不自動執行。
"""

from __future__ import annotations

from seo_advisor.autopilot.models import CostEstimateItem, RiskLevel

# 同意後「可以」自動執行的動作類型（本地、可回滾、低風險）。
_ALLOWED_ACTION_KINDS = {
    "generate_local_report",
    "generate_local_image",
    "generate_content_draft",
    "build_utm_urls",
    "build_dry_run_plan",
    "pause_low_performing_ad",  # 降低花費方向、可回滾
    "decrease_ad_budget",  # 降低花費方向、可回滾
}

# 永遠不自動執行的動作類型（不論是否同意）。
_BLOCKED_ACTION_KINDS = {
    "delete_data",
    "delete_campaign",
    "delete_files",
    "activate_new_ad",
    "increase_ad_budget_over_limit",
    "payment",
    "purchase",
    "upgrade_plan",
    "send_email",
    "send_message",
    "publish_content",
    "modify_dns",
    "modify_ssl",
    "modify_server",
    "modify_database",
    "irreversible",
}


class ConsentError(ValueError):
    """同意確認字串不符合要求時拋出。"""


def is_auto_executable(item: CostEstimateItem, action_kind: str) -> bool:
    """判斷某個成本明細項目在同意後是否可自動執行。

    需同時滿足：動作類型在白名單、不在黑名單、可回滾、風險非 critical、
    且明細本身標記 execution_allowed_after_consent。
    """
    if action_kind in _BLOCKED_ACTION_KINDS:
        return False
    if action_kind not in _ALLOWED_ACTION_KINDS:
        return False
    if not item.reversible:
        return False
    if item.risk_level == RiskLevel.CRITICAL:
        return False
    return item.execution_allowed_after_consent


def build_consent_phrase(max_authorized_minor_units: int | None, currency: str | None) -> str:
    """產生使用者需要輸入的同意確認字串。涉及金額時要求打出上限金額。"""
    base = "APPROVE AUTO EXECUTION"
    if max_authorized_minor_units and currency:
        # 金額以主要貨幣單位呈現（minor units / 100）讓使用者好懂
        major = max_authorized_minor_units / 100
        return f"{base} MAX {currency} {major:g}"
    return f"{base}"


def verify_consent(user_input: str, expected_phrase: str) -> bool:
    """驗證使用者輸入是否與預期同意字串完全一致（去頭尾空白、不分大小寫）。"""
    return user_input.strip().upper() == expected_phrase.strip().upper()
