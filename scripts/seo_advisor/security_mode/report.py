"""Security Mode 報告產出：Markdown + JSON。"""

from __future__ import annotations

from seo_advisor.security_mode.models import SecurityReport

_SEVERITY_ORDER = {"S0": 0, "S1": 1, "S2": 2, "S3": 3}

_SEVERITY_LABELS = {
    "S0": "S0 危急",
    "S1": "S1 高風險",
    "S2": "S2 中風險",
    "S3": "S3 低風險",
}


def render_security_report_markdown(report: SecurityReport) -> str:
    lines = [
        f"# 資安健檢報告：{report.target_url}",
        "",
        f"產生時間：{report.generated_at}",
        "",
    ]

    if report.passive_only:
        lines.append("> 本次為被動模式（`--passive-only`），未執行暴露檔案/目錄列表探測。")
        lines.append("")

    if not report.findings:
        lines.append("沒有發現需要留意的資安問題。")
        return "\n".join(lines)

    sorted_findings = sorted(report.findings, key=lambda f: _SEVERITY_ORDER.get(f.severity.value, 9))

    lines.append(f"## 發現摘要（共 {len(sorted_findings)} 項）")
    lines.append("")
    for finding in sorted_findings:
        severity_label = _SEVERITY_LABELS.get(finding.severity.value, finding.severity.value)
        lines.append(f"### [{severity_label}] {finding.title}")
        lines.append("")
        lines.append(f"- 類別：{finding.category}")
        lines.append(f"- SEO 影響面向：{finding.seo_impact.value}")
        lines.append(f"- 信心水準：{finding.confidence:.0%}")
        if finding.affected_urls:
            lines.append(f"- 影響位置：{', '.join(finding.affected_urls)}")
        lines.append(f"- 建議處理：{finding.recommendation}")
        if finding.needs_credential_rotation:
            lines.append("- ⚠️ **建議更換相關憑證/密碼**")
        lines.append("")

    if report.coverage_notes:
        lines.append("## 掃描涵蓋範圍備註")
        lines.append("")
        for note in report.coverage_notes:
            lines.append(f"- {note}")
        lines.append("")

    if report.skipped_checks:
        lines.append(f"未執行的檢查項目：{', '.join(sorted(set(report.skipped_checks)))}")

    return "\n".join(lines)


def render_security_report_json(report: SecurityReport) -> str:
    return report.model_dump_json(indent=2)
