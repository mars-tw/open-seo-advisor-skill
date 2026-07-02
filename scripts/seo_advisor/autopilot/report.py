"""autopilot 報告渲染：白話懶人包 + 完整報告。"""

from __future__ import annotations

from seo_advisor.autopilot.models import AutopilotDeliverable

_RISK_LABEL = {"low": "低", "medium": "中", "high": "高", "critical": "極高"}

# 把內部的 execution_mode 轉成新手看得懂、不會覺得「什麼都沒做」的人話標籤。
_MODE_LABEL = {
    "真實掃描": "已完成掃描",
    "純邏輯": "已完成分析",
    "mock": "示範資料",
    "plan-only": "已產生行動計畫",
}


def _mode_label(mode: str) -> str:
    return _MODE_LABEL.get(mode, mode)


def render_autopilot_beginner_md(d: AutopilotDeliverable) -> str:
    """給完全新手看的懶人包：3 分鐘看懂最重要的事。"""
    lines = [f"# 一鍵顧問報告（給你的白話懶人包）：{d.target}", ""]
    lines.append("> 這份是給完全不懂技術的人看的。不需要懂 SEO、廣告或程式，照著讀就好。")
    lines.append("")

    lines.append("## 一句話結論")
    lines.append("")
    lines.append(d.executive_summary)
    lines.append("")

    lines.append("## 這次幫你做了什麼")
    lines.append("")
    for r in d.module_results:
        lines.append(f"- [{_mode_label(r.execution_mode)}] {r.summary}")
    lines.append("")
    lines.append(
        "> 標示說明：「已產生行動計畫」代表這次已幫你整理出「該做什麼」的具體方向，"
        "但還沒實際跑完整掃描或動用付費功能——照著上面每項後面的指令就能拿到完整結果。"
    )
    lines.append("")

    lines.append("## 會不會花到錢？（最重要，請看）")
    lines.append("")
    cost = d.cost_estimate
    lines.append(cost.plain_language_summary)
    lines.append("")
    if cost.items:
        for item in cost.items:
            money = _money(item)
            lines.append(f"- **{item.action_summary}**（{money}，風險：{_RISK_LABEL.get(item.risk_level.value, item.risk_level.value)}）")
            lines.append(f"  - {item.user_facing_explanation}")
        lines.append("")
    else:
        lines.append("這次沒有任何會花錢的動作，全部都是免費的分析與建議。")
        lines.append("")

    lines.append("## 接下來你可以做什麼")
    lines.append("")
    for step in d.next_steps:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def render_autopilot_md(d: AutopilotDeliverable) -> str:
    """完整報告（給想看細節或交給團隊的人）。"""
    lines = [f"# 一鍵顧問完整報告：{d.target}", ""]
    lines.append(f"- 產生時間：{d.generated_at}")
    lines.append(f"- 出動模組：{', '.join(d.modules_run)}")
    lines.append(f"- 是否已同意執行：{'是' if d.consented else '否'}")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append("")
    lines.append(d.executive_summary)
    lines.append("")

    lines.append("## 各專家分析結果")
    lines.append("")
    for r in d.module_results:
        lines.append(f"### {r.module}（{_mode_label(r.execution_mode)}）")
        lines.append("")
        lines.append(r.summary)
        for h in r.highlights:
            lines.append(f"- {h}")
        lines.append("")

    lines.append("## 成本與影響明細")
    lines.append("")
    cost = d.cost_estimate
    lines.append(cost.plain_language_summary)
    lines.append("")
    if cost.items:
        lines.append("| 動作 | 類別 | 金額/費用 | 估算 | 風險 | 可回滾 | 同意後自動執行 |")
        lines.append("|---|---|---|---|---|---|---|")
        for item in cost.items:
            lines.append(
                f"| {item.action_summary} | {item.category.value} | {_money(item)} | "
                f"{item.confidence.value} | {_RISK_LABEL.get(item.risk_level.value, item.risk_level.value)} | "
                f"{'是' if item.reversible else '否'} | "
                f"{'是' if item.execution_allowed_after_consent else '否（只產計畫）'} |"
            )
        lines.append("")
    if cost.unknown_cost_items:
        lines.append("**無法精確估算的成本（只會產計畫、不自動執行）：**")
        for u in cost.unknown_cost_items:
            lines.append(f"- {u}")
        lines.append("")

    lines.append("## 執行紀錄")
    lines.append("")
    for a in d.executed_actions:
        lines.append(f"- [{a.status}] {a.summary}：{a.detail}")
    lines.append("")

    lines.append("## 下一步")
    lines.append("")
    for step in d.next_steps:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def _money(item) -> str:
    if item.amount_minor_units is not None and item.currency:
        return f"{item.amount_minor_units / 100:g} {item.currency}"
    if item.token_estimate:
        return f"約 {item.token_estimate} tokens"
    return "費用未定（預估）"


def render_cost_estimate_md(cost) -> str:
    """把成本明細渲染成新手看得懂的 Markdown（配合 CLI 主推 md、JSON 給自動化）。"""
    lines = ["# 這次會不會花錢？（成本與影響明細）", ""]
    lines.append(cost.plain_language_summary)
    lines.append("")
    if not cost.items:
        lines.append("這次沒有任何會花錢、寫入或發布的動作，全部都是免費的分析與建議。")
        return "\n".join(lines) + "\n"

    for i, item in enumerate(cost.items, start=1):
        lines.append(f"## {i}. {item.action_summary}")
        lines.append("")
        lines.append(f"- 可能費用：{_money(item)}")
        lines.append(f"- 風險：{_RISK_LABEL.get(item.risk_level.value, item.risk_level.value)}")
        lines.append(f"- 可回滾：{'可以' if item.reversible else '不可'}")
        lines.append(f"- 說明：{item.user_facing_explanation}")
        lines.append("")
    if cost.unknown_cost_items:
        lines.append("## 無法精確估算的成本（只會產計畫、不自動執行）")
        lines.append("")
        for u in cost.unknown_cost_items:
            lines.append(f"- {u}")
        lines.append("")
    return "\n".join(lines)
