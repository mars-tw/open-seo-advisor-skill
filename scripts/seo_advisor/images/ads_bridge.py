"""廣告報告 → 產圖 brief 的橋接：把素材疲勞等問題自動轉成 ImageGenerationRequest。

讓 `seo-advisor image from-ads ads-report.json` 能「廣告診斷發現素材疲勞 →
直接產新素材方向」。

設計重點（避免誤導使用者花錢產無用素材）：
- 只有「產新素材能解決」的問題才納入（creative_fatigue，或明確含素材訊號的 performance）。
- tracking / budget / audience / structure 一律排除——這些不是產圖能修的。
- 產出的是「該測哪些新創意角度」（痛點/情境/證據型），不是換顏色的微調。
- 沒有素材問題時友善停止，不硬產圖 brief。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from seo_advisor.ads.models import AdsReport
from seo_advisor.images.models import (
    AspectRatio,
    ImageGenerationRequest,
    ImageUseCase,
)

CreativeOpportunityType = Literal["creative_refresh", "ctr_recovery", "message_match"]

# 只有這些 category 可能轉成素材機會。
_CREATIVE_CATEGORIES = {"creative_fatigue", "performance", "audience"}

# performance/audience 需含這些訊號才視為「素材能解決」。
_CREATIVE_SIGNALS = (
    "素材",
    "創意",
    "creative",
    "ctr",
    "點擊率",
    "hook",
    "圖",
    "banner",
    "影片",
    "video",
    "疲勞",
    "frequency",
    "頻率",
    "fatigue",
    "visual",
    "asset",
    "image",
    "thumbnail",
    "thumb",
)

# 建議測試的創意角度（對應蒸餾的付費廣告方法論：變體要覆蓋不同角度而非換色）。
_ANGLE_POOL = ["pain_point", "benefit_outcome", "social_proof"]
_ANGLE_LABEL = {
    "pain_point": "痛點型（呈現使用者的問題情境）",
    "benefit_outcome": "成果型（使用後的具體好處）",
    "social_proof": "信任型（真實評論/數據，不得捏造）",
    "product_context": "情境型（產品在真實使用場景中）",
}

_SEVERITY_WEIGHT = {"P0": 80, "P1": 60, "P2": 35, "P3": 10}


class CreativeOpportunity(BaseModel):
    opportunity_id: str
    opportunity_type: CreativeOpportunityType
    entity_ids: list[str] = Field(default_factory=list)
    severity: str
    priority_score: float
    fatigue_reason: str
    suggested_angles: list[str]
    related_finding_ids: list[str] = Field(default_factory=list)
    source_notes: str
    needs_human_confirm: bool = False


class NoCreativeOpportunityError(ValueError):
    """廣告報告沒有明確素材缺口，不應硬產圖時拋出。"""


def _is_creative_finding(f) -> bool:
    if f.category not in _CREATIVE_CATEGORIES:
        return False
    if f.category == "creative_fatigue":
        return True
    text = f"{f.title}{f.recommendation}".lower()
    return any(sig in text for sig in _CREATIVE_SIGNALS)


def _score(f) -> float:
    score = _SEVERITY_WEIGHT.get(f.severity, 10)
    if f.category == "creative_fatigue":
        score += 30
    elif f.category == "performance":
        score += 15
    ev = f.evidence or {}
    try:
        if float(ev.get("frequency", 0)) >= 3:
            score += 10
    except (TypeError, ValueError):
        pass
    if "ctr" in ev or "ctr_drop" in ev:
        score += 10
    if f.entity_ids:
        score += 5
    return float(score)


def extract_creative_opportunities(ads_report: AdsReport) -> list[CreativeOpportunity]:
    """從廣告報告萃取適合交給 Image Material 的素材機會，依優先分數排序。"""
    opportunities: list[CreativeOpportunity] = []
    for i, f in enumerate(ads_report.findings):
        if not _is_creative_finding(f):
            continue
        # 低信心（需人工確認）的情況：
        # - performance/audience 類：本質可能是受眾/落地頁/追蹤問題，非素材
        # - creative_fatigue 但缺 frequency≥3 且無 CTR 佐證
        # - 沒有明確 evidence 佐證
        ev = f.evidence or {}
        has_fatigue_evidence = _num(ev.get("frequency")) >= 3 or "ctr" in ev or "ctr_drop" in ev
        low_confidence = (
            f.category in ("performance", "audience")
            or (f.category == "creative_fatigue" and not has_fatigue_evidence)
            or not ev
        )
        opportunities.append(
            CreativeOpportunity(
                opportunity_id=f"CRE-{i + 1:03d}",
                opportunity_type="creative_refresh",
                entity_ids=list(f.entity_ids),
                severity=f.severity,
                priority_score=_score(f),
                fatigue_reason=f.title,
                suggested_angles=list(_ANGLE_POOL),
                related_finding_ids=[f.id],
                source_notes=_finding_note(f),
                needs_human_confirm=low_confidence or not f.entity_ids,
            )
        )
    opportunities.sort(key=lambda o: o.priority_score, reverse=True)
    return opportunities


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _finding_note(f) -> str:
    entities = "、".join(f.entity_ids[:5]) or "（未指定廣告實體）"
    return (
        f"- {f.severity} / {f.category}: {f.title}\n"
        f"  涉及廣告：{entities}\n"
        f"  診斷建議：{f.recommendation}"
    )


def build_image_request_from_ads(
    ads_report: AdsReport,
    *,
    angle_override: str | None = None,
    aspect_ratio: str = "1:1",
    variants: int = 3,
    brand: str | None = None,
) -> tuple[ImageGenerationRequest, CreativeOpportunity]:
    """選最高分素材機會，轉成 ImageGenerationRequest。回傳 (request, 主要機會)。"""
    opportunities = extract_creative_opportunities(ads_report)
    if not opportunities:
        raise NoCreativeOpportunityError(
            "這份廣告報告的主要問題不是素材（可能是追蹤、預算、受眾或活動結構），"
            "產新圖無法直接解決。建議先處理那些問題；若你仍要產素材，請改用 "
            "seo-advisor image generate 直接指定 prompt。"
        )

    primary = opportunities[0]
    angles = [angle_override] if angle_override else primary.suggested_angles
    prompt = _build_prompt(ads_report, primary, angles)

    try:
        parsed_aspect = AspectRatio(aspect_ratio)
    except ValueError:
        parsed_aspect = AspectRatio.SQUARE

    from seo_advisor.images.models import BrandKit

    request = ImageGenerationRequest(
        prompt=prompt,
        use_case=ImageUseCase.META_AD,
        aspect_ratio=parsed_aspect,
        variants=max(1, min(variants, 10)),
        brand_kit=BrandKit(brand_name=brand) if brand else None,
        safety_notes=[
            "廣告素材上架前須由人工確認是否符合平台廣告政策與當地法規。",
            "不得誇大療效、保證成效或捏造數據/評論。",
        ],
    )
    return request, primary


def _build_prompt(ads_report, opp: CreativeOpportunity, angles: list[str]) -> str:
    angle_desc = "、".join(_ANGLE_LABEL.get(a, a) for a in angles)
    entities = "、".join(opp.entity_ids[:5]) or "（未指定廣告實體，請人工確認適用活動）"
    confirm = "\n（注意：此素材機會信心較低，請先人工確認是否真的是素材問題。）" if opp.needs_human_confirm else ""
    return (
        "為 Meta 廣告產生新的素材方向。目標不是微調顏色，而是測試不同的創意角度。\n\n"
        f"廣告帳戶健康分數：{ads_report.account_health_score:.0f}/100\n"
        "廣告診斷發現的素材問題：\n"
        f"- {opp.fatigue_reason}\n"
        f"- 涉及廣告：{entities}\n\n"
        f"請產生可用於 Meta 廣告的圖像素材，覆蓋這些創意角度：{angle_desc}。\n"
        "視覺要求：主體清楚、預留少量文字空間、行動裝置可讀、品牌視覺一致。\n"
        "務必避免：誇大療效或保證、誤導、冒用品牌、過多文字、廉價庫存照感。"
        f"{confirm}"
    )
