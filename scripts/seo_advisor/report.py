"""Report 產出：把 Finding[] 組成 Report 物件，並渲染成 Markdown。"""

from __future__ import annotations

import json

from seo_advisor.models import Finding, Mode, Report, ReportTarget
from seo_advisor.scoring import compute_site_health_score, group_by_severity, top_findings


def build_report(
    *,
    report_id: str,
    generated_at: str,
    target: ReportTarget,
    mode: Mode,
    findings: list[Finding],
    coverage_notes: list[str] | None = None,
    scan_stats: dict | None = None,
) -> Report:
    health_score = compute_site_health_score(findings)
    top = top_findings(findings, limit=10)

    summary = _build_executive_summary(target, health_score, findings)

    return Report(
        report_id=report_id,
        generated_at=generated_at,
        target=target,
        mode=mode,
        executive_summary=summary,
        site_health_score=health_score,
        findings=findings,
        top_findings=[f.id for f in top],
        coverage_notes=coverage_notes or [],
        scan_stats=scan_stats or {},
    )


def _build_executive_summary(target: ReportTarget, health_score: float, findings: list[Finding]) -> str:
    if not findings:
        return f"{target.identifier} 本次檢查未發現需要處理的問題，網站健康分數為 {health_score}/100。"

    grouped = group_by_severity(findings)
    p0_count = len(grouped["P0"])
    p1_count = len(grouped["P1"])

    parts = [f"{target.identifier} 的整體 SEO 健康分數為 {health_score}/100。"]
    if p0_count:
        parts.append(f"發現 {p0_count} 個阻斷級（P0）問題，需要立即處理。")
    if p1_count:
        parts.append(f"另有 {p1_count} 個高影響（P1）問題建議優先排入近期排程。")
    if not p0_count and not p1_count:
        parts.append("沒有發現阻斷級或高影響問題，主要是中低影響的優化項目。")
    parts.append(f"本次共產出 {len(findings)} 項發現，詳見下方分級清單。")
    return " ".join(parts)


def render_markdown(report: Report) -> str:
    lines: list[str] = []
    lines.append(f"# SEO 健檢報告：{report.target.identifier}")
    lines.append("")
    lines.append(f"- 報告 ID：`{report.report_id}`")
    lines.append(f"- 產生時間：{report.generated_at}")
    lines.append(f"- 模式：{report.mode.value}")
    lines.append(f"- 來源類型：{report.target.source_type}")
    if report.target.industry_profile:
        lines.append(f"- 產業設定：{report.target.industry_profile}")
    if report.target.locale:
        lines.append(f"- 語言/地區：{report.target.locale}")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append("")
    lines.append(report.executive_summary)
    lines.append("")

    lines.append("## Site Health Score")
    lines.append("")
    lines.append(f"**{report.site_health_score} / 100**")
    lines.append("")

    lines.append("## Top Findings")
    lines.append("")
    top_lookup = {f.id: f for f in report.findings}
    if report.top_findings:
        for finding_id in report.top_findings:
            finding = top_lookup.get(finding_id)
            if finding:
                lines.append(
                    f"- **[{finding.severity.value}] {finding.title}** "
                    f"(impact={finding.impact}, effort={finding.effort}, "
                    f"confidence={finding.confidence:.2f}) — `{finding.id}`"
                )
    else:
        lines.append("（無）")
    lines.append("")

    lines.append("## 完整發現清單（依優先順序分組）")
    lines.append("")
    grouped = group_by_severity(report.findings)
    for severity in ["P0", "P1", "P2", "P3"]:
        items = grouped[severity]
        lines.append(f"### {severity}（{len(items)} 項）")
        lines.append("")
        if not items:
            lines.append("（無）")
            lines.append("")
            continue
        for finding in items:
            lines.append(f"#### {finding.title} `{finding.id}`")
            lines.append("")
            lines.append(f"- 分類：{finding.category}")
            lines.append(
                f"- Impact: {finding.impact} / Effort: {finding.effort} / "
                f"Confidence: {finding.confidence:.2f}"
            )
            if finding.affected_urls:
                sample = ", ".join(finding.affected_urls[:5])
                more = f"（等共 {len(finding.affected_urls)} 個）" if len(finding.affected_urls) > 5 else ""
                lines.append(f"- 受影響 URL：{sample}{more}")
            lines.append(f"- 建議：{finding.recommendation}")
            if finding.validation:
                lines.append(f"- 驗證方式：{'; '.join(finding.validation)}")
            if finding.owner:
                lines.append(f"- 建議負責模式：{finding.owner.value}")
            lines.append("")

    if report.coverage_notes:
        lines.append("## 檢查範圍說明")
        lines.append("")
        for note in report.coverage_notes:
            lines.append(f"- {note}")
        lines.append("")

    if report.scan_stats:
        lines.append("## 掃描統計")
        lines.append("")
        for key, value in report.scan_stats.items():
            lines.append(f"- {key}: {value}")
        lines.append("")

    return "\n".join(lines)


def render_json(report: Report) -> str:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
