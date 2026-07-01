from seo_advisor.models import Finding, Mode, Severity
from seo_advisor.scoring import compute_site_health_score, group_by_severity, sort_findings


def _finding(id_, severity, impact=3, effort=2, confidence=0.9):
    return Finding(
        id=id_,
        title=f"test finding {id_}",
        mode=Mode.CONSULTANT,
        category="indexability",
        severity=severity,
        impact=impact,
        effort=effort,
        confidence=confidence,
        affected_urls=[],
        evidence={},
        recommendation="fix it",
    )


def test_sort_findings_orders_by_severity_then_priority_score():
    findings = [
        _finding("SEO-A-001", Severity.P2, impact=5, effort=1),
        _finding("SEO-B-001", Severity.P0, impact=1, effort=5),
        _finding("SEO-C-001", Severity.P1, impact=5, effort=1),
    ]
    sorted_findings = sort_findings(findings)
    assert [f.id for f in sorted_findings] == ["SEO-B-001", "SEO-C-001", "SEO-A-001"]


def test_compute_site_health_score_no_findings_is_100():
    assert compute_site_health_score([]) == 100.0


def test_compute_site_health_score_decreases_with_severity():
    p0_score = compute_site_health_score([_finding("X-001", Severity.P0, confidence=1.0)])
    p3_score = compute_site_health_score([_finding("X-002", Severity.P3, confidence=1.0)])
    assert p0_score < p3_score


def test_compute_site_health_score_never_below_zero():
    findings = [_finding(f"X-{i:03d}", Severity.P0, confidence=1.0) for i in range(10)]
    assert compute_site_health_score(findings) == 0.0


def test_group_by_severity_includes_all_levels():
    grouped = group_by_severity([_finding("X-001", Severity.P1)])
    assert set(grouped.keys()) == {"P0", "P1", "P2", "P3"}
    assert len(grouped["P1"]) == 1
    assert len(grouped["P0"]) == 0
