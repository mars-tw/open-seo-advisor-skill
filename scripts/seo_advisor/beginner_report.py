"""白話文報告層：把技術報告轉譯成完全不懂 SEO/技術的人也能看懂的版本。

設計原則（見 docs/content_writer_guide.md 的精神延伸）：
- 不假設讀者知道任何 SEO 術語（canonical、sitemap、robots.txt...）。
- 用「房屋健檢」比喻貫穿整份白話報告，讓 P0-P3 的意義直覺可理解。
- 只保留「現在最該做的事」，技術細節一律導回完整版 report.md。
"""

from __future__ import annotations

from seo_advisor.models import Finding, Report, Severity

_SEVERITY_EXPLANATION = {
    Severity.P0: (
        "今天就要處理",
        "就像家裡漏水或跳電，已經影響到基本功能，"
        "搜尋引擎或使用者可能因此進不來、找不到頁面，建議立刻處理。",
    ),
    Severity.P1: (
        "這週要處理",
        "就像大門門鎖故障或電線老舊，還能勉強使用，"
        "但已經明顯影響別人找到你、信任你的程度，建議盡快排入這週的工作。",
    ),
    Severity.P2: (
        "排進近期改善",
        "就像屋內動線或收納不太順，不影響基本生活，"
        "但整理過後體驗會更好，建議排進近期的改善清單。",
    ),
    Severity.P3: (
        "有空再優化",
        "就像牆面掉漆或家具擺放可以更好看，"
        "不會讓網站『停擺』，但處理後會讓整體更專業、更完善。",
    ),
}

_SCORE_BANDS = [
    (90, 101, "健檢結果很不錯", "網站基礎體質健康，可以把心力放在內容與成長型優化上。"),
    (75, 90, "大致健康，但有小問題待處理", "還有幾個問題會拖慢網站被搜尋引擎看見的速度，建議儘快處理。"),
    (60, 75, "需要花點心思整理", "搜尋引擎可能沒辦法完整理解你的網站，建議優先處理排在前面的項目。"),
    (40, 60, "有明顯風險，建議優先處理", "目前的問題可能已經影響網站被搜尋到的機會，建議先處理技術問題再談成長。"),
    (0, 40, "健檢紅字偏多，建議優先處理技術問題", "目前的狀況類似房子基礎工程沒打好，建議先穩住地基，再談裝潢與行銷。"),
]


def _score_band(score: float) -> tuple[str, str]:
    for low, high, headline, detail in _SCORE_BANDS:
        if low <= score < high:
            return headline, detail
    return _SCORE_BANDS[0][2], _SCORE_BANDS[0][3]


def _pick_top_actions(findings: list[Finding], limit: int = 3) -> list[Finding]:
    severity_order = {Severity.P0: 0, Severity.P1: 1, Severity.P2: 2, Severity.P3: 3}
    ranked = sorted(findings, key=lambda f: (severity_order[f.severity], -f.priority_score))
    return ranked[:limit]


def _display_name(report: Report) -> str:
    """本地路徑對新手來說太長太雜，只顯示資料夾/檔案名稱；網址則原樣顯示。"""
    identifier = report.target.identifier
    if report.target.source_type == "local_archive":
        return identifier.rstrip("/\\").replace("\\", "/").rsplit("/", 1)[-1] or identifier
    return identifier


def render_beginner_markdown(report: Report) -> str:
    lines: list[str] = []
    lines.append(f"# {_display_name(report)} 的網站體檢報告（給非技術人員看的版本）")
    lines.append("")
    lines.append(
        "> 這份報告用「房屋健檢」的比喻來解釋網站狀況，不需要懂任何 SEO 或程式術語也能看懂。"
        "如果你是工程師或 SEO 顧問，請直接看同一個資料夾裡的 `report.md`（完整技術版）。"
    )
    lines.append("")

    headline, detail = _score_band(report.site_health_score)
    lines.append("## 一句話結論")
    lines.append("")
    lines.append(
        f"把「{_display_name(report)}」想像成一間房子，搜尋引擎和使用者就是上門的訪客。"
        f"這次健檢的總分是 **{report.site_health_score:.0f} / 100**，"
        f"結論是：**{headline}**。{detail}"
    )
    lines.append("")

    lines.append("## 網站健康分數：這個數字代表什麼？")
    lines.append("")
    lines.append(f"### {report.site_health_score:.0f} / 100")
    lines.append("")
    lines.append("| 分數區間 | 代表意義 |")
    lines.append("|---|---|")
    for low, high, band_headline, band_detail in _SCORE_BANDS:
        range_label = f"{low}-{high - 1 if high <= 100 else 100}"
        lines.append(f"| {range_label} | {band_headline}：{band_detail} |")
    lines.append("")

    lines.append("## 最該先處理的事")
    lines.append("")
    top_actions = _pick_top_actions(report.findings)
    if not top_actions:
        lines.append("這次健檢沒有發現需要處理的問題，網站目前狀況良好。")
    else:
        for i, finding in enumerate(top_actions, start=1):
            _, severity_detail = _SEVERITY_EXPLANATION[finding.severity]
            lines.append(f"{i}. **{finding.title}**")
            lines.append(f"   - 白話說明：{severity_detail}")
            lines.append(f"   - 具體怎麼做：{finding.recommendation}")
            lines.append("")

    lines.append("## 優先順序怎麼看？（房屋健檢比喻）")
    lines.append("")
    lines.append("我們把每個問題分成四個等級，就像房屋健檢報告一樣：")
    lines.append("")
    for severity in [Severity.P0, Severity.P1, Severity.P2, Severity.P3]:
        urgency, meaning = _SEVERITY_EXPLANATION[severity]
        count = sum(1 for f in report.findings if f.severity == severity)
        lines.append(f"- **{severity.value}（{urgency}，本次發現 {count} 項）**：{meaning}")
    lines.append("")

    lines.append("## 想看完整技術細節？")
    lines.append("")
    lines.append(
        "這份白話報告只挑出最重要的重點。如果你要交給工程師或 SEO 顧問處理，"
        "請提供同一個資料夾中的：\n"
        "- `report.md`：完整技術報告，包含每一項問題的詳細證據與驗證方式\n"
        "- `report.json`：機器可讀格式，方便串接其他工具或自動化流程\n"
        "- 看不懂的名詞可以查 `docs/glossary-for-beginners.md` 的白話對照表"
    )
    lines.append("")

    if report.coverage_notes:
        lines.append("## 小提醒")
        lines.append("")
        lines.append("這次健檢有些項目還沒檢查到（工具持續開發中），包括：")
        for note in report.coverage_notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines)
