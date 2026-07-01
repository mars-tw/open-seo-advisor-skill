from seo_advisor.beginner_report import render_beginner_markdown
from seo_advisor.models import Finding, Mode, ReportTarget, Severity
from seo_advisor.report import build_report


def _finding(id_="SEO-A-001", severity=Severity.P1, title="測試問題"):
    return Finding(
        id=id_,
        title=title,
        mode=Mode.CONSULTANT,
        category="indexability",
        severity=severity,
        impact=4,
        effort=2,
        confidence=0.9,
        affected_urls=["https://example.com/a"],
        evidence={},
        recommendation="修正這個問題的具體做法",
    )


def _build(findings):
    target = ReportTarget(source_type="http", identifier="https://example.com")
    return build_report(
        report_id="r1",
        generated_at="2026-07-01T00:00:00Z",
        target=target,
        mode=Mode.CONSULTANT,
        findings=findings,
    )


def test_beginner_report_has_one_sentence_conclusion():
    report = _build([_finding()])
    md = render_beginner_markdown(report)
    assert "一句話結論" in md


def test_beginner_report_explains_score_bands():
    report = _build([])
    md = render_beginner_markdown(report)
    assert "分數區間" in md
    assert "健檢結果很不錯" in md  # 滿分應落在最高區間


def test_beginner_report_no_findings_says_all_good():
    report = _build([])
    md = render_beginner_markdown(report)
    assert "沒有發現需要處理的問題" in md


def test_beginner_report_lists_top_actions_with_house_metaphor():
    report = _build([_finding(severity=Severity.P0, title="網站完全打不開")])
    md = render_beginner_markdown(report)
    assert "網站完全打不開" in md
    assert "今天就要處理" in md


def test_beginner_report_avoids_jargon_only_terms_without_explanation():
    report = _build([_finding()])
    md = render_beginner_markdown(report)
    # 應該引導去看完整技術報告，而不是直接丟術語
    assert "report.md" in md
    assert "glossary-for-beginners.md" in md


def test_beginner_report_severity_legend_covers_all_levels():
    report = _build([_finding(severity=s) for s in [Severity.P0, Severity.P1, Severity.P2, Severity.P3]])
    md = render_beginner_markdown(report)
    for label in ["P0", "P1", "P2", "P3"]:
        assert label in md
