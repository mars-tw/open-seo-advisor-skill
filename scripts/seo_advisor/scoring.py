"""Finding 排序與 Site Health Score 計算。

規則見 config/scoring.yaml 與 docs/architecture.md：
- 先依 severity（P0 > P1 > P2 > P3）分組
- 同組內依 priority_score = impact * confidence / effort 由高到低排序
"""

from __future__ import annotations

from seo_advisor.models import Finding, Severity

_SEVERITY_ORDER = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}

_SEVERITY_PENALTY = {
    Severity.P0: 25.0,
    Severity.P1: 10.0,
    Severity.P2: 4.0,
    Severity.P3: 1.0,
}


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """依 severity 分組，組內依 priority_score 由高到低排序。"""
    return sorted(
        findings,
        key=lambda f: (_SEVERITY_ORDER[f.severity], -f.priority_score),
    )


def top_findings(findings: list[Finding], limit: int = 10) -> list[Finding]:
    return sort_findings(findings)[:limit]


def compute_site_health_score(findings: list[Finding]) -> float:
    """依嚴重度加權扣分計算 0-100 的健康分數，下限為 0。"""
    score = 100.0
    for finding in findings:
        penalty = _SEVERITY_PENALTY[finding.severity] * finding.confidence
        score -= penalty
    return max(0.0, round(score, 1))


def group_by_severity(findings: list[Finding]) -> dict[str, list[Finding]]:
    grouped: dict[str, list[Finding]] = {level.value: [] for level in Severity}
    for finding in sort_findings(findings):
        grouped[finding.severity.value].append(finding)
    return grouped
