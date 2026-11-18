import json

from seo_advisor.writers.models import ContentRequest, LLMRequest
from seo_advisor.writers.pipeline import run_content_writer_pipeline
from seo_advisor.writers.providers.mock import MockProvider

_BRIEF_JSON = json.dumps(
    {
        "primary_intent": "informational",
        "secondary_intents": [],
        "reader_tasks": ["了解如何選擇適合的 SEO 顧問"],
        "must_cover_questions": ["SEO 顧問服務通常包含哪些項目"],
        "content_gaps": [],
        "eeat_needs": ["實際案例"],
        "is_ymyl": False,
        "facts_needing_verification": [],
    }
)

_OUTLINE_JSON = json.dumps(
    {
        "sections": [
            {"heading": "什麼是 SEO 顧問服務", "level": 2, "goal": "定義服務範圍"},
            {"heading": "如何挑選適合的顧問", "level": 2, "goal": "提供挑選標準"},
        ],
        "title_variants": ["如何挑選 SEO 顧問：完整指南"],
        "meta_description_variants": ["了解如何挑選適合的 SEO 顧問服務"],
        "schema_recommendation": "Article",
        "internal_link_plan": ["連到服務頁面"],
    }
)

_QA_JSON = json.dumps(
    {
        "passed": True,
        "quality_score": 85,
        "issues": [],
        "human_review_notes": ["建議請領域專家再確認案例細節"],
    }
)

_DRAFT_TEXT = "# 如何挑選 SEO 顧問\n\n這是一篇關於挑選 SEO 顧問的文章草稿。"


def _sequential_mock_provider():
    responses = iter([_BRIEF_JSON, _OUTLINE_JSON, _DRAFT_TEXT, _QA_JSON])

    def factory(request: LLMRequest) -> str:
        return next(responses)

    return MockProvider(factory)


def test_full_pipeline_runs_all_four_stages():
    provider = _sequential_mock_provider()
    request = ContentRequest(topic="SEO 顧問服務怎麼挑選")

    progress_messages: list[str] = []
    result = run_content_writer_pipeline(provider, request, on_progress=progress_messages.append)

    assert result.brief.primary_intent.value == "informational"
    assert len(result.outline.sections) == 2
    assert "SEO 顧問" in result.draft_markdown
    assert result.qa.quality_score == 85
    assert any("brief" in msg for msg in progress_messages)
    assert any("outline" in msg for msg in progress_messages)
    assert any("draft" in msg for msg in progress_messages)
    assert any("QA" in msg for msg in progress_messages)


def test_pipeline_without_auto_revise_has_no_revised_draft():
    provider = _sequential_mock_provider()
    request = ContentRequest(topic="test", auto_revise=False)

    result = run_content_writer_pipeline(provider, request)
    assert result.revised_markdown is None


def test_pipeline_result_records_provider_id():
    provider = _sequential_mock_provider()
    request = ContentRequest(topic="test")

    result = run_content_writer_pipeline(provider, request)
    assert result.provider == "mock"


def test_pipeline_result_records_actual_model_used():
    # model 應該來自實際 LLMResponse.model，而非猜測 provider 的私有屬性
    provider = _sequential_mock_provider()
    request = ContentRequest(topic="test")

    result = run_content_writer_pipeline(provider, request)
    assert result.model == "mock-model"


def test_writing_review_and_revision_keep_original_product_evidence():
    qa = json.loads(_QA_JSON)
    qa.update(passed=False, issues=[dict(category="trust", severity="P1",
              description="確認尺寸", recommendation="查閱型錄")])
    responses = iter([_BRIEF_JSON, _OUTLINE_JSON, _DRAFT_TEXT, json.dumps(qa), "# 修訂完成", _QA_JSON])
    prompts = []

    def respond(request):
        prompts.append(request.messages[0].content)
        return next(responses)

    request = ContentRequest(topic="零件選型", source_notes="型錄 R32：只適用 A63",
                             brand_context="North Demo", target_url="/parts/63",
                             internal_links=["/selector"], auto_revise=True)
    result = run_content_writer_pipeline(MockProvider(respond), request)
    assert result.revised_markdown == "# 修訂完成"
    assert result.qa.passed and not result.initial_qa.passed
    assert result.revised_markdown in prompts[-1]
    for prompt in prompts:
        for value in (request.source_notes, request.brand_context, request.target_url, "/selector"):
            assert value in prompt
    assert all("連到服務頁面" in prompt for prompt in prompts[2:])
