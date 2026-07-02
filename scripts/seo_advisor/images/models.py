"""GPT 產圖素材專家（Image Material Mode）的資料模型。

放在獨立模組，與 Consultant 的爬蟲模型、Content Writer 的寫作模型分離，
各自服務不同關注點。圖像生成的 provider 抽象設計刻意對照
seo_advisor/writers/providers 的 LLMProvider，讓兩者的心智模型一致。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ImageUseCase(str, Enum):
    META_AD = "meta_ad"
    SOCIAL = "social"
    BLOG_HERO = "blog_hero"
    BLOG_INLINE = "blog_inline"
    OG_IMAGE = "og_image"
    LANDING_PAGE = "landing_page"


class AspectRatio(str, Enum):
    SQUARE = "1:1"
    PORTRAIT_4_5 = "4:5"
    STORY_9_16 = "9:16"
    LANDSCAPE_16_9 = "16:9"
    LANDSCAPE_3_2 = "3:2"
    PORTRAIT_2_3 = "2:3"


class BrandKit(BaseModel):
    """品牌視覺規範，供 prompt builder 產生一致的素材。"""

    brand_name: str | None = None
    primary_colors: list[str] = Field(default_factory=list)
    tone: str | None = None  # 例如 "專業", "活潑", "極簡"
    style: str | None = None  # 例如 "photo", "illustration", "3d", "editorial"
    forbidden_elements: list[str] = Field(default_factory=list)


class ImageGenerationRequest(BaseModel):
    prompt: str
    use_case: ImageUseCase = ImageUseCase.SOCIAL
    model: str | None = None
    aspect_ratio: AspectRatio = AspectRatio.SQUARE
    output_format: str = "png"  # png | webp | jpeg
    quality: str = "medium"  # low | medium | high | auto
    variants: int = Field(default=1, ge=1, le=10)
    brand_kit: BrandKit | None = None
    negative_prompt: str | None = None
    safety_notes: list[str] = Field(default_factory=list)


class ImageArtifact(BaseModel):
    id: str
    path: str
    provider: str
    model: str
    prompt: str
    revised_prompt: str | None = None
    width: int
    height: int
    aspect_ratio: str
    output_format: str
    use_case: str
    variant_label: str
    usage: dict = Field(default_factory=dict)
    compliance_notes: list[str] = Field(default_factory=list)


class ImageGenerationResult(BaseModel):
    request: ImageGenerationRequest
    artifacts: list[ImageArtifact] = Field(default_factory=list)
    provider: str
    model: str
    compliance_notes: list[str] = Field(default_factory=list)
    human_review_required: bool = False
    ai_generated_disclosure_suggestion: str = (
        "本圖像由 AI 生成，建議在使用時依當地規範揭露為 AI 生成內容。"
    )
