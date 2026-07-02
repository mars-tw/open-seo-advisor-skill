"""Content Writer Mode 核心流程：brief -> outline -> draft -> QA（-> 可選 revise）。

四個階段各呼叫一次 LLM（revise 只在需要時額外呼叫一次），每個階段的輸入
都來自前一階段的結構化輸出，確保 draft 有大綱依據、QA 有草稿依據，而不是
互相獨立、缺乏上下文的四次呼叫。
"""

from __future__ import annotations

from typing import Callable

from seo_advisor.writers.models import (
    ContentBrief,
    ContentOutline,
    ContentRequest,
    ContentWriterResult,
    EditorialIssue,
    EditorialQA,
    LLMMessage,
    LLMRequest,
)
from seo_advisor.writers.prompts import (
    brief_system_prompt,
    brief_user_prompt,
    draft_system_prompt,
    draft_user_prompt,
    outline_system_prompt,
    outline_user_prompt,
    qa_system_prompt,
    qa_user_prompt,
)
from seo_advisor.writers.providers.base import LLMProvider
from seo_advisor.writers.quality import run_structural_checks

ProgressCallback = Callable[[str], None]

_BRIEF_SCHEMA = {
    "type": "object",
    "required": ["primary_intent", "reader_tasks", "must_cover_questions", "is_ymyl"],
    "properties": {
        "primary_intent": {
            "type": "string",
            "enum": ["informational", "commercial", "transactional", "navigational", "local", "mixed"],
        },
        "secondary_intents": {"type": "array", "items": {"type": "string"}},
        "reader_tasks": {"type": "array", "items": {"type": "string"}},
        "must_cover_questions": {"type": "array", "items": {"type": "string"}},
        "content_gaps": {"type": "array", "items": {"type": "string"}},
        "eeat_needs": {"type": "array", "items": {"type": "string"}},
        "is_ymyl": {"type": "boolean"},
        "facts_needing_verification": {"type": "array", "items": {"type": "string"}},
    },
}

_OUTLINE_SCHEMA = {
    "type": "object",
    "required": ["sections"],
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["heading", "level"],
                "properties": {
                    "heading": {"type": "string"},
                    "level": {"type": "integer"},
                    "goal": {"type": "string"},
                },
            },
        },
        "title_variants": {"type": "array", "items": {"type": "string"}},
        "meta_description_variants": {"type": "array", "items": {"type": "string"}},
        "schema_recommendation": {"type": ["string", "null"]},
        "internal_link_plan": {"type": "array", "items": {"type": "string"}},
    },
}

_QA_SCHEMA = {
    "type": "object",
    "required": ["passed", "quality_score", "issues"],
    "properties": {
        "passed": {"type": "boolean"},
        "quality_score": {"type": "number"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["category", "severity", "description", "recommendation"],
                "properties": {
                    "category": {"type": "string"},
                    "severity": {"type": "string"},
                    "description": {"type": "string"},
                    "recommendation": {"type": "string"},
                },
            },
        },
        "human_review_notes": {"type": "array", "items": {"type": "string"}},
    },
}


def _noop(_: str) -> None:
    return None


def _generate_brief(provider: LLMProvider, request: ContentRequest) -> ContentBrief:
    llm_request = LLMRequest(
        system=brief_system_prompt(),
        messages=[LLMMessage(role="user", content=brief_user_prompt(request))],
    )
    response = provider.complete_json(llm_request, _BRIEF_SCHEMA)
    return ContentBrief.model_validate(response.json_data)


def _generate_outline(
    provider: LLMProvider, request: ContentRequest, brief: ContentBrief
) -> ContentOutline:
    llm_request = LLMRequest(
        system=outline_system_prompt(),
        messages=[LLMMessage(role="user", content=outline_user_prompt(request, brief))],
    )
    response = provider.complete_json(llm_request, _OUTLINE_SCHEMA)
    return ContentOutline.model_validate(response.json_data)


def _generate_draft(
    provider: LLMProvider, request: ContentRequest, brief: ContentBrief, outline: ContentOutline
) -> tuple[str, str]:
    """回傳 (草稿文字, 實際使用的模型名稱)。"""
    llm_request = LLMRequest(
        system=draft_system_prompt(),
        messages=[LLMMessage(role="user", content=draft_user_prompt(request, brief, outline))],
        max_tokens=6000,
    )
    response = provider.complete(llm_request)
    return response.text, response.model


def _generate_qa(provider: LLMProvider, request: ContentRequest, draft_markdown: str) -> EditorialQA:
    llm_request = LLMRequest(
        system=qa_system_prompt(),
        messages=[LLMMessage(role="user", content=qa_user_prompt(request, draft_markdown))],
    )
    response = provider.complete_json(llm_request, _QA_SCHEMA)
    llm_qa = EditorialQA.model_validate(response.json_data)

    # 併入程式化結構檢查的結果，這些是 LLM 可能疏漏但規則明確的問題
    # （例如多個 H1、YMYL 關鍵字命中），不依賴 LLM 的語意判斷。
    structural_issues = run_structural_checks(draft_markdown)
    combined_issues = list(llm_qa.issues) + structural_issues
    passed = llm_qa.passed and not any(i.severity in {"P0", "P1"} for i in structural_issues)

    return EditorialQA(
        passed=passed,
        quality_score=llm_qa.quality_score,
        issues=combined_issues,
        human_review_notes=llm_qa.human_review_notes,
    )


def _revise_draft(
    provider: LLMProvider, request: ContentRequest, draft_markdown: str, issues: list[EditorialIssue]
) -> str:
    issue_summary = "\n".join(f"- [{i.severity}] {i.description}：{i.recommendation}" for i in issues)
    llm_request = LLMRequest(
        system=draft_system_prompt(),
        messages=[
            LLMMessage(
                role="user",
                content=(
                    f"以下是關於「{request.topic}」的草稿，請根據審稿意見修正後"
                    f"輸出完整修訂版（Markdown）：\n\n草稿：\n{draft_markdown}\n\n"
                    f"審稿意見：\n{issue_summary}"
                ),
            )
        ],
        max_tokens=6000,
    )
    response = provider.complete(llm_request)
    return response.text


def run_content_writer_pipeline(
    provider: LLMProvider,
    request: ContentRequest,
    *,
    on_progress: ProgressCallback = _noop,
) -> ContentWriterResult:
    on_progress("第 1/4 步：分析搜尋意圖與內容缺口（brief）")
    brief = _generate_brief(provider, request)

    on_progress("第 2/4 步：規劃文章大綱與 SEO 中繼資料（outline）")
    outline = _generate_outline(provider, request, brief)

    on_progress("第 3/4 步：撰寫文章草稿（draft）")
    draft_markdown, model_used = _generate_draft(provider, request, brief, outline)

    on_progress("第 4/4 步：品質審核（QA）")
    qa = _generate_qa(provider, request, draft_markdown)

    revised_markdown: str | None = None
    if request.auto_revise and not qa.passed and qa.issues:
        on_progress("發現需要修正的問題，正在自動修訂草稿")
        revised_markdown = _revise_draft(provider, request, draft_markdown, qa.issues)

    return ContentWriterResult(
        request=request,
        brief=brief,
        outline=outline,
        draft_markdown=draft_markdown,
        qa=qa,
        revised_markdown=revised_markdown,
        provider=provider.id(),
        model=model_used,
    )
