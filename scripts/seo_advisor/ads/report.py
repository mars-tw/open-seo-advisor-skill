"""把廣告診斷結果渲染成 Markdown 報告與 JSON。"""

from __future__ import annotations

import json

from seo_advisor.ads.models import AdsActionPlan, AdsReport

_SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def render_ads_report_markdown(report: AdsReport) -> str:
    lines: list[str] = []
    lines.append(f"# Meta 廣告健檢報告：{report.account.name or report.account.account_id}")
    lines.append("")
    lines.append(f"- 帳戶：{report.account.account_id}（{report.account.currency}）")
    lines.append(f"- 觀察期間：最近 {report.observation_days} 天")
    lines.append(f"- 產生時間：{report.generated_at}")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append("")
    lines.append(report.executive_summary)
    lines.append("")

    lines.append("## 帳戶健康分數")
    lines.append("")
    lines.append(f"**{report.account_health_score:.0f} / 100**")
    lines.append("")

    lines.append("## 發現與建議（依優先順序）")
    lines.append("")
    ranked = sorted(report.findings, key=lambda f: _SEVERITY_ORDER.get(f.severity, 9))
    if not ranked:
        lines.append("在本次觀察範圍內沒有發現需要處理的問題。")
    for finding in ranked:
        lines.append(f"### [{finding.severity}] {finding.title}")
        lines.append("")
        lines.append(f"- 分類：{finding.category}")
        if finding.entity_ids:
            lines.append(f"- 相關實體：{', '.join(finding.entity_ids)}")
        lines.append(f"- 建議：{finding.recommendation}")
        lines.append("")

    return "\n".join(lines)


def render_ads_report_json(report: AdsReport) -> str:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)


def render_action_plan_json(plan: AdsActionPlan) -> str:
    return json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2)
