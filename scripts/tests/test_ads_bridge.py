"""廣告報告 → 產圖 brief 串接的測試，重點在「不把非素材問題誤轉成產圖」。"""

import pytest

from seo_advisor.ads.models import AdsAccountProfile, AdsFinding, AdsReport
from seo_advisor.images.ads_bridge import (
    NoCreativeOpportunityError,
    build_image_request_from_ads,
    extract_creative_opportunities,
)
from seo_advisor.images.models import ImageUseCase


def _finding(fid, category, title, rec="建議", severity="P2", entities=None, evidence=None):
    return AdsFinding(
        id=fid, title=title, category=category, severity=severity,
        entity_ids=entities or [], evidence=evidence or {}, recommendation=rec,
    )


def _report(findings, score=70.0):
    return AdsReport(
        report_id="A1",
        generated_at="2026-07-06T00:00:00Z",
        account=AdsAccountProfile(account_id="act_1"),
        account_health_score=score,
        executive_summary="test",
        findings=findings,
    )


def test_creative_fatigue_becomes_opportunity():
    r = _report([
        _finding("F1", "creative_fatigue", "圖B 素材疲勞",
                 "輪替新素材角度", entities=["ad_1"], evidence={"frequency": 7.8, "ctr": 0.24}),
    ])
    opps = extract_creative_opportunities(r)
    assert len(opps) == 1
    assert opps[0].entity_ids == ["ad_1"]


def test_tracking_and_budget_excluded():
    """追蹤/預算問題不是產圖能解，必須排除。"""
    r = _report([
        _finding("F1", "tracking", "Pixel 事件遺失", "修正 CAPI 設定"),
        _finding("F2", "budget", "預算浪費在低效渠道", "調整預算分配"),
        _finding("F3", "structure", "活動結構混亂", "重整 CBO"),
    ])
    assert extract_creative_opportunities(r) == []


def test_performance_without_creative_signal_excluded():
    """ROAS 低但沒提到素材/CTR → 可能是追蹤/落地頁問題，不該產圖。"""
    r = _report([
        _finding("F1", "performance", "ROAS 偏低", "檢查轉換追蹤與落地頁"),
    ])
    assert extract_creative_opportunities(r) == []


def test_performance_with_ctr_signal_included():
    r = _report([
        _finding("F1", "performance", "CTR 明顯下降", "測試新的素材 hook 與創意角度"),
    ])
    assert len(extract_creative_opportunities(r)) == 1


def test_no_creative_opportunity_raises():
    r = _report([_finding("F1", "budget", "預算浪費", "調整分配")])
    with pytest.raises(NoCreativeOpportunityError):
        build_image_request_from_ads(r)


def test_build_request_uses_meta_ad_use_case():
    r = _report([
        _finding("F1", "creative_fatigue", "素材疲勞", "換素材",
                 entities=["ad_1"], evidence={"frequency": 5, "ctr": 0.3}),
    ])
    request, primary = build_image_request_from_ads(r)
    assert request.use_case == ImageUseCase.META_AD
    assert request.variants == 3
    # prompt 應該要求測試不同角度，而非換顏色
    assert "不是微調顏色" in request.prompt or "創意角度" in request.prompt


def test_low_confidence_flagged_when_no_fatigue_evidence():
    """creative_fatigue 但沒有 frequency/CTR 證據 → 標記需人工確認。"""
    r = _report([
        _finding("F1", "creative_fatigue", "可能素材老化", "考慮換素材", entities=["ad_1"]),
    ])
    opps = extract_creative_opportunities(r)
    assert opps[0].needs_human_confirm is True


def test_performance_opportunity_marked_low_confidence():
    """performance 類即使含素材訊號，仍標低信心（本質可能是受眾/落地頁問題）。"""
    r = _report([
        _finding("F1", "performance", "CTR 下降", "測試新素材 hook", entities=["ad_1"],
                 evidence={"ctr": 0.3}),
    ])
    opps = extract_creative_opportunities(r)
    assert opps[0].needs_human_confirm is True


def test_fatigue_with_strong_evidence_not_low_confidence():
    r = _report([
        _finding("F1", "creative_fatigue", "素材疲勞", "換素材", entities=["ad_1"],
                 evidence={"frequency": 6, "ctr": 0.2}),
    ])
    opps = extract_creative_opportunities(r)
    assert opps[0].needs_human_confirm is False


def test_safety_notes_present():
    r = _report([
        _finding("F1", "creative_fatigue", "素材疲勞", "換素材",
                 entities=["ad_1"], evidence={"frequency": 5}),
    ])
    request, _ = build_image_request_from_ads(r)
    assert any("廣告政策" in n or "法規" in n for n in request.safety_notes)
