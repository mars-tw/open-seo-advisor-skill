"""成長行銷模組的執行協調：UTM 計畫、CRO 診斷、成效分析。

CRO 有 URL 但沒 HTML 時，會透過 HTTPConnector 抓取頁面（read-only），
再交給 cro.analyze_landing_page 分析。
"""

from __future__ import annotations

import datetime
from pathlib import Path

from seo_advisor.growth.analytics import analyze_metrics, compute_summary
from seo_advisor.growth.cro import analyze_landing_page
from seo_advisor.growth.models import AnalyticsReport, AnalyticsSource, CroReport, UtmPlan
from seo_advisor.growth.providers.factory import create_analytics_provider
from seo_advisor.growth.report import (
    render_cro_report_json,
    render_cro_report_markdown,
    render_utm_plan_json,
    render_utm_plan_markdown,
)
from seo_advisor.growth.utm import build_utm_plan


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _write(out_dir: str, stem: str, md: str, json_text: str) -> tuple[Path, Path]:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    md_path = out_path / f"{stem}.md"
    json_path = out_path / f"{stem}.json"
    md_path.write_text(md, encoding="utf-8")
    json_path.write_text(json_text, encoding="utf-8")
    return md_path, json_path


def run_utm(base_url: str, channels: list[str], out_dir: str) -> tuple[UtmPlan, Path, Path]:
    plan = build_utm_plan(base_url, channels)
    md_path, json_path = _write(
        out_dir, "utm-plan", render_utm_plan_markdown(plan), render_utm_plan_json(plan)
    )
    return plan, md_path, json_path


def run_cro(url: str, out_dir: str, *, fetch: bool = True) -> tuple[CroReport, Path, Path]:
    html: str | None = None
    if fetch and url.startswith(("http://", "https://")):
        html = _try_fetch_html(url)
    report = analyze_landing_page(html, url)
    md_path, json_path = _write(
        out_dir, "cro-report", render_cro_report_markdown(report), render_cro_report_json(report)
    )
    return report, md_path, json_path


def run_analytics(
    provider_name: str, property_id: str, since_days: int, out_dir: str
) -> tuple[AnalyticsReport, Path, Path]:
    import json

    provider = create_analytics_provider(provider_name)
    rows = provider.fetch_metrics(property_id, since_days)
    findings = analyze_metrics(rows)
    try:
        source = AnalyticsSource(provider.id())
    except ValueError:
        source = AnalyticsSource.MOCK
    report = AnalyticsReport(
        source=source,
        property_id=property_id,
        date_range=f"last_{since_days}d",
        rows=rows,
        findings=findings,
        summary=compute_summary(rows, findings),
    )
    md = _render_analytics_markdown(report)
    json_text = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    md_path, json_path = _write(out_dir, "analytics-report", md, json_text)
    return report, md_path, json_path


def _try_fetch_html(url: str) -> str | None:
    try:
        from seo_advisor.connectors.http import HTTPConnector

        connector = HTTPConnector(url)
        try:
            snapshot = connector.fetch_url(url, fetched_at=_now_iso())
            return snapshot.html or None
        finally:
            connector.close()
    except Exception:  # noqa: BLE001 - 抓不到就退回純規劃，不讓 CRO 中斷
        return None


def _render_analytics_markdown(report: AnalyticsReport) -> str:
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    lines = [f"# 跨渠道成效分析報告：{report.property_id}", ""]
    lines.append(f"- 資料來源：{report.source.value}")
    lines.append(f"- 期間：{report.date_range}")
    lines.append("")
    lines.append("## 摘要")
    lines.append("")
    lines.append(report.summary)
    lines.append("")
    lines.append("## 各渠道成效")
    lines.append("")
    lines.append("| 渠道 | Sessions | 轉換 | 轉換率 | 成本 | 營收 |")
    lines.append("|---|--:|--:|--:|--:|--:|")
    for row in report.rows:
        cost = row.cost_minor_units if row.cost_minor_units is not None else "-"
        rev = row.revenue_minor_units if row.revenue_minor_units is not None else "-"
        lines.append(
            f"| {row.channel} | {row.sessions} | {row.conversions} | "
            f"{row.conversion_rate:.2%} | {cost} | {rev} |"
        )
    lines.append("")
    lines.append("## 成效問題與建議（依優先順序）")
    lines.append("")
    for f in sorted(report.findings, key=lambda x: order.get(x.severity.value, 9)):
        lines.append(f"### [{f.severity.value}][{f.category}] {f.title}")
        lines.append("")
        lines.append(f"- 建議：{f.recommendation}")
        lines.append("")
    return "\n".join(lines)
