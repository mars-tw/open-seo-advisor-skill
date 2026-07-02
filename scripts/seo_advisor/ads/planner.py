"""把 AdsFinding 轉換成 dry-run 的 AdsActionPlan。

安全底線：planner 只產生「計畫」（預設 dry_run=True），永遠不會實際呼叫
Meta 寫入 API。而且只把「安全的」建議動作納入計畫——會擴大花費的動作
（增加預算、啟用投放、暫停整個活動）即使 analyzer 建議了，也會被
AdsSafetyPolicy 擋掉、只在報告中作為建議呈現，不進入自動化計畫。

整體流程強制為：audit → plan（dry-run）→ 人工審核 → 精確確認 → apply。
"""

from __future__ import annotations

from seo_advisor.ads.models import (
    AdsAccountProfile,
    AdsAction,
    AdsActionPlan,
    AdsActionType,
    AdsFinding,
    AdsSafetyPolicy,
    InsightsRow,
)

# 只有這些「不會擴大花費」的動作類型可以進入自動化計畫。
# 增加預算、啟用投放、暫停整個活動屬於高風險，一律不自動排入計畫。
_SAFE_ACTION_TYPES = {
    AdsActionType.PAUSE_AD,
    AdsActionType.DECREASE_DAILY_BUDGET,
}


def build_action_plan(
    account: AdsAccountProfile,
    findings: list[AdsFinding],
    insights: list[InsightsRow],
    *,
    policy: AdsSafetyPolicy,
    plan_id: str,
    generated_at: str,
) -> AdsActionPlan:
    insights_by_id = {row.entity_id: row for row in insights}
    actions: list[AdsAction] = []
    seq = 0

    for finding in findings:
        action_type = finding.suggested_action_type
        if action_type is None or action_type not in _SAFE_ACTION_TYPES:
            continue
        if len(actions) >= policy.max_actions_per_run:
            break

        entity_id = finding.entity_ids[0] if finding.entity_ids else ""
        row = insights_by_id.get(entity_id)
        if row is None:
            continue

        seq += 1
        if action_type == AdsActionType.PAUSE_AD:
            actions.append(
                AdsAction(
                    action_id=f"{plan_id}-act-{seq:03d}",
                    type=action_type,
                    entity_type=row.entity_type,
                    entity_id=entity_id,
                    entity_name=row.name,
                    before={"status": row.status.value},
                    after={"status": "PAUSED"},
                    budget_delta_minor_units=0,
                    risk_level=finding.severity,
                    reason=finding.title,
                    rollback_snapshot={"status": row.status.value},
                )
            )

    pause_count = sum(1 for a in actions if a.type == AdsActionType.PAUSE_AD)
    if pause_count > policy.max_pause_ads_per_run:
        actions = actions[: policy.max_pause_ads_per_run]

    total_budget_delta = sum(a.budget_delta_minor_units for a in actions)
    confirmation = policy_confirmation_phrase(account, total_budget_delta)

    return AdsActionPlan(
        plan_id=plan_id,
        account_id=account.account_id,
        dry_run=policy.dry_run,
        generated_at=generated_at,
        currency=account.currency,
        actions=actions,
        total_budget_delta_minor_units=total_budget_delta,
        required_confirmation=confirmation,
        rollback_required=policy.rollback_log_required,
    )


def policy_confirmation_phrase(account: AdsAccountProfile, total_budget_delta_minor_units: int) -> str:
    return (
        f"APPLY {account.account_id} "
        f"MAX_BUDGET_DELTA={total_budget_delta_minor_units} {account.currency} DRY_RUN=false"
    )
