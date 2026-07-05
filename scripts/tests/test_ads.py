import json

import pytest

from seo_advisor.ads.analyzer import analyze_ads, compute_account_health_score
from seo_advisor.ads.models import (
    AdsAccountProfile,
    AdsActionType,
    AdsSafetyPolicy,
    InsightsRow,
)
from seo_advisor.ads.planner import build_action_plan
from seo_advisor.ads.providers.base import AdsProviderError
from seo_advisor.ads.providers.factory import create_ads_provider
from seo_advisor.ads.runner import run_ads_plan


# --- SafetyPolicy 防護 ---

def test_policy_blocks_budget_increase_by_default():
    policy = AdsSafetyPolicy()
    with pytest.raises(PermissionError):
        policy.require_action_allowed(AdsActionType.INCREASE_DAILY_BUDGET)


def test_policy_blocks_activate_by_default():
    policy = AdsSafetyPolicy()
    with pytest.raises(PermissionError):
        policy.require_action_allowed(AdsActionType.ACTIVATE_ENTITY)


def test_policy_blocks_campaign_pause_by_default():
    policy = AdsSafetyPolicy()
    with pytest.raises(PermissionError):
        policy.require_action_allowed(AdsActionType.PAUSE_CAMPAIGN)


def test_policy_allows_pause_ad():
    policy = AdsSafetyPolicy()
    policy.require_action_allowed(AdsActionType.PAUSE_AD)  # 不應拋出


def test_policy_rejects_write_in_dry_run():
    policy = AdsSafetyPolicy(dry_run=True)
    with pytest.raises(PermissionError):
        policy.require_write_not_dry_run()


def test_policy_rejects_disallowed_account():
    policy = AdsSafetyPolicy(allowed_ad_accounts=["act_allowed"])
    with pytest.raises(PermissionError):
        policy.require_account_allowed("act_other")


# --- Provider ---

def test_create_mock_ads_provider():
    provider = create_ads_provider("mock")
    assert provider.id() == "mock"
    assert provider.capabilities() == {"ads_read"}


def test_meta_provider_requires_token(monkeypatch):
    monkeypatch.delenv("META_ACCESS_TOKEN", raising=False)
    with pytest.raises(AdsProviderError):
        create_ads_provider("meta")


def test_mock_provider_apply_actions_is_blocked():
    provider = create_ads_provider("mock")
    with pytest.raises(AdsProviderError):
        provider.apply_actions(plan=None, confirmation="x")  # read-only provider 拒絕寫入


# --- Analyzer 診斷 ---

def _account(has_pixel=True, events=None):
    return AdsAccountProfile(
        account_id="act_test",
        has_pixel=has_pixel,
        tracked_events=events if events is not None else ["Purchase"],
    )


def test_analyzer_flags_low_roas():
    insights = [
        InsightsRow(
            entity_id="ad_x", entity_type="ad", name="虧損廣告",
            spend_minor_units=800000, impressions=200000, clicks=1800,
            conversions=8, conversion_value_minor_units=400000, days_active=21,
        )
    ]
    findings = analyze_ads(_account(), insights, policy=AdsSafetyPolicy())
    assert any("ROAS" in f.title and f.severity == "P1" for f in findings)


def test_analyzer_flags_missing_pixel_as_p0():
    findings = analyze_ads(_account(has_pixel=False), [], policy=AdsSafetyPolicy())
    assert any(f.category == "tracking" and f.severity == "P0" for f in findings)


def test_analyzer_skips_low_data_entities():
    insights = [
        InsightsRow(
            entity_id="ad_new", entity_type="ad", name="新廣告",
            spend_minor_units=100, impressions=500, clicks=5,
            conversions=0, days_active=1,
        )
    ]
    findings = analyze_ads(_account(), insights, policy=AdsSafetyPolicy())
    # 資料不足的實體應被標為 P3「暫不建議調整」，而非給出激進建議
    low_data = [f for f in findings if "資料不足" in f.title]
    assert low_data and low_data[0].severity == "P3"


# --- Planner 安全性 ---

def test_planner_excludes_budget_increase_actions():
    """擴量候選（增加預算）即使被 analyzer 建議，也不應進入自動化 dry-run 計畫。"""
    insights = [
        InsightsRow(
            entity_id="ad_star", entity_type="ad", name="明星廣告",
            spend_minor_units=150000, impressions=80000, clicks=1600,
            conversions=40, conversion_value_minor_units=1200000, days_active=30,
        )
    ]
    account = _account()
    findings = analyze_ads(account, insights, policy=AdsSafetyPolicy())
    plan = build_action_plan(
        account, findings, insights, policy=AdsSafetyPolicy(),
        plan_id="p1", generated_at="2026-07-02T00:00:00Z",
    )
    assert all(a.type != AdsActionType.INCREASE_DAILY_BUDGET for a in plan.actions)


def test_planner_plan_is_dry_run_and_zero_budget_delta():
    provider = create_ads_provider("mock")
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        outcome = run_ads_plan(
            provider, account_id="act_demo", since_days=30, out_dir=d,
            policy=AdsSafetyPolicy(),
        )
    assert outcome.plan.dry_run is True
    assert outcome.plan.total_budget_delta_minor_units == 0
    # 所有動作都應有 rollback snapshot
    assert all(a.rollback_snapshot for a in outcome.plan.actions)


def test_planner_actions_only_contain_safe_types():
    provider = create_ads_provider("mock")
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        outcome = run_ads_plan(
            provider, account_id="act_demo", since_days=30, out_dir=d,
            policy=AdsSafetyPolicy(),
        )
    safe_types = {AdsActionType.PAUSE_AD, AdsActionType.DECREASE_DAILY_BUDGET}
    assert all(a.type in safe_types for a in outcome.plan.actions)


def test_health_score_penalizes_p0_most():
    from seo_advisor.ads.models import AdsFinding

    p0_score = compute_account_health_score([AdsFinding(id="x", title="t", category="tracking", severity="P0", recommendation="r")])
    p3_score = compute_account_health_score([AdsFinding(id="y", title="t", category="performance", severity="P3", recommendation="r")])
    assert p0_score < p3_score


def test_plan_json_is_written(tmp_path):
    provider = create_ads_provider("mock")
    outcome = run_ads_plan(
        provider, account_id="act_demo", since_days=30, out_dir=str(tmp_path),
        policy=AdsSafetyPolicy(),
    )
    data = json.loads(outcome.plan_json_path.read_text(encoding="utf-8"))
    assert data["dry_run"] is True


# --- 數值驗證：負數應被 Pydantic 拒絕，避免預算保護失效 ---

def test_ads_safety_policy_rejects_negative_budget_cap():
    import pytest
    from pydantic import ValidationError

    from seo_advisor.ads.models import AdsSafetyPolicy

    with pytest.raises(ValidationError):
        AdsSafetyPolicy(max_total_budget_delta_minor_units_per_run=-1)


def test_ads_metric_rejects_negative_spend():
    import pytest
    from pydantic import ValidationError

    from seo_advisor.ads.models import InsightsRow

    with pytest.raises(ValidationError):
        InsightsRow(entity_id="1", entity_type="ad", spend_minor_units=-5)
