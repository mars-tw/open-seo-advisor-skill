"""把 UTM 計畫與 CRO 報告渲染成 Markdown。"""

from __future__ import annotations

import json

from seo_advisor.growth.models import CroReport, UtmPlan

_SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def render_utm_plan_markdown(plan: UtmPlan) -> str:
    lines = [f"# UTM 追蹤與歸因計畫：{plan.base_url}", ""]
    lines.append("## 各渠道 tagged URL")
    lines.append("")
    for channel, params in plan.params_by_channel.items():
        url = next((u for u in plan.tagged_urls if f"utm_content={channel}" in u), "")
        lines.append(f"- **{channel}**（source={params.source} / medium={params.medium}）：{url}")
    lines.append("")

    lines.append("## 命名規範建議")
    lines.append("")
    for rec in plan.naming_recommendations:
        lines.append(f"- {rec}")
    lines.append("")

    if plan.audit_items:
        lines.append("## 歸因衛生檢查")
        lines.append("")
        for item in sorted(plan.audit_items, key=lambda i: _SEVERITY_ORDER.get(i.severity.value, 9)):
            lines.append(f"- [{item.severity.value}] {item.message} → {item.recommendation}")
        lines.append("")
    return "\n".join(lines)


def render_utm_plan_json(plan: UtmPlan) -> str:
    return json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2)


def render_cro_report_markdown(report: CroReport) -> str:
    lines = [f"# 落地頁 CRO 診斷與 A/B 測試計畫：{report.landing_url}", ""]

    lines.append("## 轉換率優化發現（依優先順序）")
    lines.append("")
    for f in sorted(report.findings, key=lambda x: _SEVERITY_ORDER.get(x.severity.value, 9)):
        lines.append(f"### [{f.severity.value}][{f.category}] {f.title}")
        lines.append("")
        if f.evidence:
            lines.append(f"- 觀察：{f.evidence}")
        lines.append(f"- 建議：{f.recommendation}")
        lines.append("")

    lines.append("## 建議的 A/B 測試")
    lines.append("")
    for idea in report.ab_test_ideas:
        lines.append(f"### 測試：{idea.element}")
        lines.append("")
        lines.append(f"- 假設：{idea.hypothesis}")
        lines.append(f"- A 版（對照）：{idea.variant_a}")
        lines.append(f"- B 版（實驗）：{idea.variant_b}")
        lines.append(f"- 主要指標：{idea.primary_metric}")
        lines.append(f"- 樣本量提醒：{idea.min_sample_hint}")
        lines.append("")

    lines.append("## 轉換假設")
    lines.append("")
    for h in report.conversion_hypotheses:
        lines.append(f"- {h}")
    lines.append("")
    return "\n".join(lines)


def render_cro_report_json(report: CroReport) -> str:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
