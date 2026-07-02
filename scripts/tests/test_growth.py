import json

import pytest

from seo_advisor.growth.analytics import analyze_metrics, compute_summary
from seo_advisor.growth.cro import analyze_landing_page
from seo_advisor.growth.models import AnalyticsMetricRow, AnalyticsSource, UtmParams
from seo_advisor.growth.providers.base import AnalyticsProviderError
from seo_advisor.growth.providers.factory import create_analytics_provider
from seo_advisor.growth.runner import run_analytics, run_cro, run_utm
from seo_advisor.growth.utm import audit_utm_urls, build_utm_plan, build_utm_url


# --- UTM ---

def test_build_utm_url_merges_existing_query():
    url = build_utm_url(
        "https://example.com/lp?ref=x",
        UtmParams(source="google", medium="cpc", campaign="c1"),
    )
    assert "ref=x" in url and "utm_source=google" in url and "utm_campaign=c1" in url


def test_audit_flags_missing_required_fields():
    items = audit_utm_urls(["https://e.com/?utm_source=google"])
    codes = {i.issue_code for i in items}
    assert "utm_required_missing" in codes


def test_audit_flags_chinese_and_mixed_case():
    items = audit_utm_urls(["https://e.com/?utm_source=Google&utm_medium=社群&utm_campaign=夏季"])
    codes = {i.issue_code for i in items}
    assert "utm_mixed_case" in codes
    assert "utm_unsafe_characters" in codes


def test_build_utm_plan_generates_tagged_urls_per_channel():
    plan = build_utm_plan("https://example.com/promo", ["google", "facebook", "email"])
    assert len(plan.tagged_urls) == 3
    assert plan.naming_recommendations


# --- CRO ---

def test_cro_with_html_detects_findings():
    html = "<html><head><title>免費試用</title></head><body><h1>提升排名</h1><a>了解更多</a></body></html>"
    report = analyze_landing_page(html, "https://example.com/lp")
    assert 3 <= len(report.findings) <= 6
    assert report.ab_test_ideas


def test_cro_missing_h1_flagged():
    html = "<html><body><p>沒有標題</p></body></html>"
    report = analyze_landing_page(html, "https://example.com/lp")
    assert any(f.category == "structure" for f in report.findings)


def test_cro_planning_only_when_no_html():
    report = analyze_landing_page(None, "https://example.com/lp")
    assert report.findings
    assert report.ab_test_ideas


# --- Analytics ---

def test_analytics_mock_provider_returns_rows():
    provider = create_analytics_provider("mock")
    rows = provider.fetch_metrics("demo", 30)
    assert len(rows) == 5


def test_analytics_provider_read_only_capability():
    provider = create_analytics_provider("mock")
    assert provider.capabilities() == {"read_metrics"}


def test_analytics_ga4_requires_credentials(monkeypatch):
    monkeypatch.delenv("GA4_PROPERTY_ID", raising=False)
    with pytest.raises(AnalyticsProviderError):
        create_analytics_provider("ga4")


def test_analyze_metrics_detects_tracking_gap():
    rows = [
        AnalyticsMetricRow(channel="c", source=AnalyticsSource.MOCK, sessions=400, conversions=0)
    ]
    findings = analyze_metrics(rows)
    assert any(f.category == "tracking" for f in findings)


def test_analyze_metrics_detects_high_cost_low_return():
    rows = [
        AnalyticsMetricRow(
            channel="ad", source=AnalyticsSource.MOCK, sessions=500,
            conversions=1, cost_minor_units=100_000, revenue_minor_units=5_000,
        )
    ]
    findings = analyze_metrics(rows)
    assert any(f.category == "spend" and f.severity.value == "P1" for f in findings)


def test_analyze_metrics_empty_returns_tracking_warning():
    findings = analyze_metrics([])
    assert findings and findings[0].category == "tracking"


def test_conversion_rate_computed_field():
    row = AnalyticsMetricRow(channel="c", sessions=100, conversions=5)
    assert row.conversion_rate == 0.05
    dumped = row.model_dump(mode="json")
    assert dumped["conversion_rate"] == 0.05


# --- runner (免金鑰) ---

def test_run_utm_writes_reports(tmp_path):
    plan, md, js = run_utm("https://example.com/x", ["google", "email"], str(tmp_path))
    assert md.exists() and js.exists()
    assert plan.tagged_urls


def test_run_cro_no_fetch(tmp_path):
    report, md, js = run_cro("https://example.com/lp", str(tmp_path), fetch=False)
    assert md.exists() and js.exists()


def test_run_analytics_mock(tmp_path):
    report, md, js = run_analytics("mock", "demo", 30, str(tmp_path))
    assert report.rows
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["source"] == "mock"


def test_compute_summary_mentions_channel_count():
    provider = create_analytics_provider("mock")
    rows = provider.fetch_metrics("demo", 30)
    summary = compute_summary(rows, analyze_metrics(rows))
    assert "渠道" in summary
