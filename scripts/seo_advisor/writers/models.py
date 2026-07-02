"""Content Writer Mode 專用的資料模型。

放在獨立模組（而非核心 seo_advisor/models.py）是因為這些模型只服務
Content Writer Mode 的 LLM 呼叫鏈，跟 Consultant Mode 的爬蟲/Finding/Report
資料模型是不同的關注點，混在一起會讓核心模型檔案越來越龐大且職責不清。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class SearchIntent(str, Enum):
    INFORMATIONAL = "informational"
    COMMERCIAL = "commercial"
    TRANSACTIONAL = "transactional"
    NAVIGATIONAL = "navigational"
    LOCAL = "local"
    MIXED = "mixed"


class LLMMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class LLMRequest(BaseModel):
    system: str
    messages: list[LLMMessage]
    model: str | None = None
    temperature: float = 0.3
    max_tokens: int | None = 4000
    response_format: str = "text"  # "text" | "json"
    timeout_seconds: int = 120


class LLMResponse(BaseModel):
    text: str
    json_data: dict | None = None
    model: str
    provider: str
    usage: dict = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ContentRequest(BaseModel):
    """使用者對 Content Writer Mode 的輸入，對應 CLI 的 `seo-advisor write` 參數。"""

    topic: str
    audience: str | None = None
    lang: str = "zh-TW"
    locale: str | None = None
    intent: SearchIntent | None = None
    industry: str | None = None
    brand_context: str | None = None
    source_notes: str | None = None
    internal_links: list[str] = Field(default_factory=list)
    target_url: str | None = None
    auto_revise: bool = False


class ContentBrief(BaseModel):
    primary_intent: SearchIntent
    secondary_intents: list[SearchIntent] = Field(default_factory=list)
    reader_tasks: list[str] = Field(default_factory=list)
    must_cover_questions: list[str] = Field(default_factory=list)
    content_gaps: list[str] = Field(default_factory=list)
    eeat_needs: list[str] = Field(default_factory=list)
    is_ymyl: bool = False
    facts_needing_verification: list[str] = Field(default_factory=list)


class OutlineSection(BaseModel):
    heading: str
    level: int = Field(ge=1, le=3)
    goal: str = ""


class ContentOutline(BaseModel):
    sections: list[OutlineSection] = Field(default_factory=list)
    title_variants: list[str] = Field(default_factory=list)
    meta_description_variants: list[str] = Field(default_factory=list)
    schema_recommendation: str | None = None
    internal_link_plan: list[str] = Field(default_factory=list)


class EditorialIssue(BaseModel):
    category: str  # 例如 content_quality, eeat, trust, localization, structure
    severity: str  # 沿用 Severity 的字串值（P0-P3），但 QA 上下文不強制轉型
    description: str
    recommendation: str


class EditorialQA(BaseModel):
    passed: bool
    quality_score: float = Field(ge=0, le=100)
    issues: list[EditorialIssue] = Field(default_factory=list)
    human_review_notes: list[str] = Field(default_factory=list)


class ContentWriterResult(BaseModel):
    request: ContentRequest
    brief: ContentBrief
    outline: ContentOutline
    draft_markdown: str
    qa: EditorialQA
    revised_markdown: str | None = None
    provider: str
    model: str
