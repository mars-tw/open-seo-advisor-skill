"""把電商 listing 分析結果渲染成 Markdown。"""

from __future__ import annotations

import json

from seo_advisor.ecommerce.models import EcommerceReport

_SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def render_ecommerce_markdown(report: EcommerceReport) -> str:
    lines = [f"# 電商 Listing 健檢報告：{report.listing_ref}", ""]
    lines.append(f"- 平台：{report.marketplace}")
    lines.append("")
    lines.append("## 健康分數")
    lines.append("")
    lines.append(f"**{report.listing_health_score:.0f} / 100**")
    lines.append("")
    lines.append("## 摘要")
    lines.append("")
    lines.append(report.summary)
    lines.append("")
    lines.append(
        "> 本報告為依方法論原則自動產生的**推測性建議**，非人工實際稽核；"
        "實際優化前建議由熟悉你商品與市場的人再確認。"
    )
    lines.append("")

    lines.append("## 發現與建議（依優先順序）")
    lines.append("")
    ranked = sorted(report.findings, key=lambda f: _SEVERITY_ORDER.get(f.severity.value, 9))
    if not ranked:
        lines.append("在本次可判斷的項目中沒有發現明顯問題。")
    for f in ranked:
        lines.append(f"### [{f.severity.value}][{f.category}] {f.title}")
        lines.append("")
        check = f.evidence.get("check")
        if check:
            lines.append(f"- 依據原則：{check}")
        lines.append(f"- 建議：{f.recommendation}")
        lines.append("")

    lines.append("## 本次套用的方法論檢核點")
    lines.append("")
    for item in report.applied_checklist:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def render_ecommerce_json(report: EcommerceReport) -> str:
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
