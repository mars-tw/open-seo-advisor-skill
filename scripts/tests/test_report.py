from seo_advisor.models import Finding, Mode, ReportTarget, Severity
from seo_advisor.report import build_report, render_json, render_markdown


def _finding(id_="SEO-A-001", severity=Severity.P1):
    return Finding(
        id=id_,
        title="測試問題",
        mode=Mode.CONSULTANT,
        category="indexability",
        severity=severity,
        impact=4,
        effort=2,
        confidence=0.9,
        affected_urls=["https://example.com/a"],
        evidence={"http_status": 404},
        recommendation="修正這個問題",
        validation=["重新爬取確認"],
    )


def test_build_report_computes_health_score_and_top_findings():
    target = ReportTarget(source_type="http", identifier="https://example.com")
    report = build_report(
        report_id="r1",
        generated_at="2026-07-01T00:00:00Z",
        target=target,
        mode=Mode.CONSULTANT,
        findings=[_finding()],
    )
    assert report.site_health_score < 100.0
    assert report.top_findings == ["SEO-A-001"]


def test_build_report_empty_findings_perfect_score():
    target = ReportTarget(source_type="http", identifier="https://example.com")
    report = build_report(
        report_id="r2",
        generated_at="2026-07-01T00:00:00Z",
        target=target,
        mode=Mode.CONSULTANT,
        findings=[],
    )
    assert report.site_health_score == 100.0
    assert "未發現需要處理的問題" in report.executive_summary


def test_render_markdown_contains_key_sections():
    target = ReportTarget(source_type="http", identifier="https://example.com")
    report = build_report(
        report_id="r3",
        generated_at="2026-07-01T00:00:00Z",
        target=target,
        mode=Mode.CONSULTANT,
        findings=[_finding()],
    )
    md = render_markdown(report)
    assert "# SEO 健檢報告" in md
    assert "## Executive Summary" in md
    assert "## Site Health Score" in md
    assert "## Top Findings" in md
    assert "SEO-A-001" in md


def test_render_json_round_trips():
    target = ReportTarget(source_type="http", identifier="https://example.com")
    report = build_report(
        report_id="r4",
        generated_at="2026-07-01T00:00:00Z",
        target=target,
        mode=Mode.CONSULTANT,
        findings=[_finding()],
    )
    import json

    data = json.loads(render_json(report))
    assert data["report_id"] == "r4"
    assert data["findings"][0]["id"] == "SEO-A-001"
