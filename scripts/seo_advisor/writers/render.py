"""把 ContentWriterResult 渲染成人類可讀的 Markdown 報告與純草稿檔案。"""

from __future__ import annotations

import json

from seo_advisor.writers.models import ContentWriterResult


def render_content_report_markdown(result: ContentWriterResult) -> str:
    lines: list[str] = []
    lines.append(f"# SEO 文章寫作報告：{result.request.topic}")
    lines.append("")
    lines.append(f"- 語言／地區：{result.request.lang}" + (f"（{result.request.locale}）" if result.request.locale else ""))
    lines.append(f"- LLM Provider：{result.provider}（模型：{result.model}）")
    lines.append("")

    lines.append("## Content Brief")
    lines.append("")
    lines.append(f"- 主要搜尋意圖：{result.brief.primary_intent.value}")
    if result.brief.secondary_intents:
        lines.append(f"- 次要意圖：{', '.join(i.value for i in result.brief.secondary_intents)}")
    if result.brief.reader_tasks:
        lines.append("- 讀者想完成的任務：")
        for task in result.brief.reader_tasks:
            lines.append(f"  - {task}")
    if result.brief.must_cover_questions:
        lines.append("- 必須回答的問題：")
        for q in result.brief.must_cover_questions:
            lines.append(f"  - {q}")
    if result.brief.is_ymyl:
        lines.append("- **⚠ 這是 YMYL 主題，發布前建議由領域專家審核。**")
    if result.brief.facts_needing_verification:
        lines.append("- 需要查證的事實：")
        for fact in result.brief.facts_needing_verification:
            lines.append(f"  - {fact}")
    lines.append("")

    lines.append("## SEO 中繼資料建議")
    lines.append("")
    if result.outline.title_variants:
        lines.append("**Title 選項：**")
        for t in result.outline.title_variants:
            lines.append(f"- {t}")
        lines.append("")
    if result.outline.meta_description_variants:
        lines.append("**Meta Description 選項：**")
        for d in result.outline.meta_description_variants:
            lines.append(f"- {d}")
        lines.append("")
    if result.outline.schema_recommendation:
        lines.append(f"**建議結構化資料類型：** {result.outline.schema_recommendation}")
        lines.append("")
    if result.outline.internal_link_plan:
        lines.append("**內部連結建議：**")
        for link in result.outline.internal_link_plan:
            lines.append(f"- {link}")
        lines.append("")

    lines.append("## 品質審核（Editorial QA）")
    lines.append("")
    status = "✅ 通過" if result.qa.passed else "⚠ 需要修正"
    lines.append(f"- 審核結果：{status}")
    lines.append(f"- 品質分數：{result.qa.quality_score:.0f} / 100")
    if result.qa.issues:
        lines.append("- 發現的問題：")
        for issue in result.qa.issues:
            lines.append(f"  - [{issue.severity}][{issue.category}] {issue.description}")
            lines.append(f"    建議：{issue.recommendation}")
    if result.qa.human_review_notes:
        lines.append("- 需要人工確認的地方：")
        for note in result.qa.human_review_notes:
            lines.append(f"  - {note}")
    lines.append("")

    lines.append("## 文章草稿")
    lines.append("")
    lines.append(result.draft_markdown)
    lines.append("")

    if result.revised_markdown:
        lines.append("## 自動修訂版草稿")
        lines.append("")
        lines.append(
            "> 以下是根據審核意見自動修訂後的版本，仍建議由人工做最終確認。"
        )
        lines.append("")
        lines.append(result.revised_markdown)
        lines.append("")

    return "\n".join(lines)


def render_content_report_json(result: ContentWriterResult) -> str:
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)


def render_final_draft_markdown(result: ContentWriterResult) -> str:
    """只回傳最終可用的草稿內容（優先用修訂版），方便直接複製貼上發布。"""
    return result.revised_markdown or result.draft_markdown
