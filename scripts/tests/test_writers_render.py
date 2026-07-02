import json

from seo_advisor.writers.models import (
    ContentBrief,
    ContentOutline,
    ContentRequest,
    ContentWriterResult,
    EditorialIssue,
    EditorialQA,
    OutlineSection,
    SearchIntent,
)
from seo_advisor.writers.render import (
    render_content_report_json,
    render_content_report_markdown,
    render_final_draft_markdown,
)


def _result(*, revised=None, passed=True, issues=None):
    return ContentWriterResult(
        request=ContentRequest(topic="測試主題"),
        brief=ContentBrief(
            primary_intent=SearchIntent.INFORMATIONAL,
            reader_tasks=["了解某件事"],
            must_cover_questions=["這是什麼"],
            is_ymyl=False,
        ),
        outline=ContentOutline(
            sections=[OutlineSection(heading="第一節", level=2, goal="介紹")],
            title_variants=["測試標題"],
            meta_description_variants=["測試描述"],
        ),
        draft_markdown="# 測試主題\n\n這是草稿內容。",
        qa=EditorialQA(passed=passed, quality_score=80, issues=issues or []),
        revised_markdown=revised,
        provider="mock",
        model="mock-model",
    )


def test_render_markdown_includes_brief_and_draft():
    md = render_content_report_markdown(_result())
    assert "Content Brief" in md
    assert "測試主題" in md
    assert "這是草稿內容" in md


def test_render_markdown_shows_qa_status_passed():
    md = render_content_report_markdown(_result(passed=True))
    assert "✅ 通過" in md


def test_render_markdown_shows_qa_status_needs_fix():
    issue = EditorialIssue(
        category="structure", severity="P1", description="缺少 H1", recommendation="補上標題"
    )
    md = render_content_report_markdown(_result(passed=False, issues=[issue]))
    assert "⚠ 需要修正" in md
    assert "缺少 H1" in md


def test_render_markdown_includes_revised_draft_when_present():
    md = render_content_report_markdown(_result(revised="# 修訂版內容"))
    assert "自動修訂版草稿" in md
    assert "修訂版內容" in md


def test_render_json_round_trips():
    data = json.loads(render_content_report_json(_result()))
    assert data["request"]["topic"] == "測試主題"
    assert data["brief"]["primary_intent"] == "informational"


def test_render_final_draft_prefers_revised_version():
    result = _result(revised="# 最終版")
    assert render_final_draft_markdown(result) == "# 最終版"


def test_render_final_draft_falls_back_to_original_draft():
    result = _result(revised=None)
    assert render_final_draft_markdown(result) == "# 測試主題\n\n這是草稿內容。"
