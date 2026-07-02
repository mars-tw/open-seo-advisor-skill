"""Amazon / 電商平台 listing 分析模型。

運用 knowledge/methodology.yaml 中「ecommerce」領域的中性化蒸餾原則，對
使用者提供的 listing 資訊做檢核。純邏輯，不需外部 API，免金鑰可用。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from seo_advisor.models import Severity

EcommerceCategory = Literal[
    "title",
    "bullets",
    "images",
    "keywords",
    "reviews",
    "ppc",
    "availability",
    "variations",
]


class EcommerceListing(BaseModel):
    title: str
    bullet_points: list[str] = Field(default_factory=list)
    description: str | None = None
    backend_keywords: list[str] = Field(default_factory=list)
    main_image_present: bool = True
    secondary_image_count: int = Field(default=0, ge=0)
    has_a_plus_content: bool = False
    review_count: int = Field(default=0, ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    price: str | None = None
    has_buy_box: bool = True
    in_stock: bool = True
    variations_count: int = Field(default=0, ge=0)


class EcommerceFinding(BaseModel):
    category: EcommerceCategory
    severity: Severity
    title: str
    evidence: dict = Field(default_factory=dict)
    recommendation: str


class EcommerceReport(BaseModel):
    marketplace: str = "amazon"
    listing_ref: str
    findings: list[EcommerceFinding] = Field(default_factory=list)
    listing_health_score: float = Field(ge=0, le=100)
    summary: str
    applied_checklist: list[str] = Field(default_factory=list)
