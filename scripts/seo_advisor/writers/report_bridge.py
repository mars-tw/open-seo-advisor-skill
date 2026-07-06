"""顧問報告 → 內容 brief 的橋接：把 SEO 缺口自動轉成 ContentRequest。

讓 `seo-advisor write --from-report report.json` 能「找到問題 → 直接產內容補洞」。

設計重點（避免產出無意義 brief）：
- 只有「內容能解決」的 finding 才轉成內容機會（content_quality / internal_linking）。
- 純技術/資安問題（4xx、canonical、noindex、security、HTTPS）一律排除。
- OG 缺失不單獨觸發主要 brief，只作為 metadata 改寫的補充背景。
- 沒有任何內容缺口時友善停止，不硬產空 brief。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from seo_advisor.models import Finding, Report, Severity
from seo_advisor.writers.models import ContentRequest, SearchIntent

OpportunityType = Literal["page_refresh", "content_expansion", "internal_linking", "metadata_batch"]

# 只有這些 category 的 finding 才可能轉成內容機會。
_CONTENT_CATEGORIES = {"content_quality", "internal_linking"}

# recommendation 含這些字樣才視為「該補內容」而非純技術修正。
_CONTENT_SIGNALS = (
    "內容",
    "標題",
    "meta",
    "描述",
    "h1",
    "文案",
    "字數",
    "薄",
    "重複",
    "faq",
    "文章",
    "段落",
    "錨文字",
    "內鏈",
    "內部連結",
)

_SEVERITY_WEIGHT = {Severity.P0: 80, Severity.P1: 60, Severity.P2: 35, Severity.P3: 10}


class ContentOpportunity(BaseModel):
    opportunity_id: str
    opportunity_type: OpportunityType
    target_url: str | None = None
    suggested_topic: str
    suggested_intent: SearchIntent = SearchIntent.INFORMATIONAL
    reason: str
    priority_score: float
    severity: Severity
    related_finding_ids: list[str] = Field(default_factory=list)
    source_notes: str
    internal_links: list[str] = Field(default_factory=list)


class NoContentOpportunityError(ValueError):
    """報告中沒有任何內容相關缺口，且使用者未指定 --topic 時拋出。"""


def _is_content_finding(f: Finding) -> bool:
    if f.category not in _CONTENT_CATEGORIES:
        return False
    text = f"{f.title}{f.recommendation}".lower()
    return any(sig in text for sig in _CONTENT_SIGNALS)


def _opportunity_type(f: Finding) -> OpportunityType:
    if f.category == "internal_linking":
        return "internal_linking"
    text = f"{f.title}{f.recommendation}".lower()
    if any(s in text for s in ("薄", "字數", "內容不足", "擴充", "段落")):
        return "content_expansion"
    if len(f.affected_urls) > 1:
        return "metadata_batch"
    return "page_refresh"


def _score(f: Finding) -> float:
    score = _SEVERITY_WEIGHT.get(f.severity, 10)
    if f.category == "content_quality":
        score += 25
    elif f.category == "internal_linking":
        score += 15
    if f.affected_urls:
        score += 10
    return float(score)


def extract_content_opportunities(report: Report) -> list[ContentOpportunity]:
    """從顧問報告萃取可交給 Content Writer 的內容機會，依優先分數排序。"""
    opportunities: list[ContentOpportunity] = []
    for i, f in enumerate(report.findings):
        if not _is_content_finding(f):
            continue
        otype = _opportunity_type(f)
        target = f.affected_urls[0] if f.affected_urls else None
        opportunities.append(
            ContentOpportunity(
                opportunity_id=f"OPP-{i + 1:03d}",
                opportunity_type=otype,
                target_url=target,
                suggested_topic=_suggest_topic(f, target, otype),
                suggested_intent=_suggest_intent(f, otype),
                reason=f.title,
                priority_score=_score(f),
                severity=f.severity,
                related_finding_ids=[f.id],
                source_notes=_finding_note(f),
                internal_links=f.affected_urls[:10] if otype == "internal_linking" else [],
            )
        )
    opportunities.sort(key=lambda o: o.priority_score, reverse=True)
    return opportunities


def _suggest_topic(f: Finding, target: str | None, otype: OpportunityType) -> str:
    # 本地掃描時 target 是相對路徑，明確標「本地路徑」避免 LLM 假裝知道正式網址。
    where = target or "全站/多頁"
    if target and target.startswith("/"):
        where = f"本地路徑 {target}"
    intent_hint = "更符合商業搜尋意圖" if _suggest_intent(f, otype) == SearchIntent.COMMERCIAL else "更符合使用者搜尋需求"

    if otype == "internal_linking":
        return f"為 {where} 補充有價值的內容，並建立自然的內部連結與錨文字"
    if otype == "content_expansion":
        return f"擴充 {where} 的內容深度與涵蓋面，使其 {intent_hint}"
    if otype == "metadata_batch":
        return "批次改寫多頁的 SEO 標題與 meta description（避免重複、提高點閱率）"
    return f"改寫 {where} 的 SEO 標題、meta description 與 H1，使其 {intent_hint}"


def _suggest_intent(f: Finding, otype: OpportunityType) -> SearchIntent:
    text = f"{f.title}{f.recommendation}".lower()
    if any(w in text for w in ("product", "商品", "價格", "購買", "landing")):
        return SearchIntent.COMMERCIAL
    return SearchIntent.INFORMATIONAL


def _finding_note(f: Finding) -> str:
    urls = "、".join(f.affected_urls[:3]) or "（未指定）"
    return (
        f"- {f.severity.value} / {f.category}: {f.title}\n"
        f"  影響頁面：{urls}\n"
        f"  顧問建議：{f.recommendation}"
    )


def build_content_request_from_report(
    report: Report,
    *,
    topic_override: str | None = None,
    audience: str | None = None,
    lang: str = "zh-TW",
    locale: str | None = None,
    industry: str | None = None,
    brand_context: str | None = None,
    auto_revise: bool = True,
) -> ContentRequest:
    """把顧問報告轉成一份 ContentRequest。使用者的 --topic 永遠優先。"""
    opportunities = extract_content_opportunities(report)

    if not opportunities and not topic_override:
        raise NoContentOpportunityError(
            "這份報告沒有發現明確的『內容可解決』缺口（多為技術或索引問題）。"
            "如果你仍想產出文章，請改用 --topic 直接指定寫作主題。"
        )

    primary = opportunities[0] if opportunities else None
    topic = topic_override or (primary.suggested_topic if primary else "")

    return ContentRequest(
        topic=topic,
        audience=audience,
        lang=lang,
        locale=locale,
        intent=primary.suggested_intent if primary else None,
        industry=industry,
        brand_context=brand_context,
        source_notes=_build_source_notes(report, opportunities, primary, topic_override),
        internal_links=primary.internal_links if primary else [],
        target_url=primary.target_url if primary else None,
        auto_revise=auto_revise,
    )


def _build_source_notes(report, opportunities, primary, topic_override) -> str:
    target = primary.target_url if primary else "全站/多頁"
    lines = [
        "[顧問報告轉內容任務]",
        f"網站健康分數：{report.site_health_score:.0f}/100",
        f"目標頁：{target}",
        "任務目的：用內容補足以下 SEO 缺口，不要泛泛寫新文章。",
        "",
        "[需要解決的 SEO 問題]",
    ]
    if opportunities and all(o.severity == Severity.P3 for o in opportunities):
        lines.insert(-1, "（註：以下皆為低優先的內容優化，非重大問題。）")
    if opportunities:
        for opp in opportunities[:5]:
            lines.append(opp.source_notes)
        if len(opportunities) > 5:
            lines.append(f"（另有 {len(opportunities) - 5} 筆相似問題未列入，請先處理以上最高優先項。）")
    else:
        lines.append("（報告未發現明確內容缺口，以下主題由使用者指定，報告僅作背景。）")

    lines += ["", "[寫作要求]"]
    ptype = primary.opportunity_type if primary else None
    if ptype == "metadata_batch":
        # 關鍵：批次 metadata 任務不要產出長文，只要 title/meta/H1 清單。
        lines += [
            "- 這是『批次改寫 metadata』任務，**不要寫一篇文章**。",
            "- 請針對每個受影響頁面，各產出一組「title / meta description / H1」草案，",
            "  彼此不重複、各自對應該頁主題。以清單形式輸出即可。",
        ]
    elif ptype == "internal_linking":
        lines += [
            "- 這是『內鏈補強』任務：請針對目標頁補一段自然、有價值的內容，",
            "  並明確列出建議的錨文字，以及應該從哪些頁面連過來（見上方目標頁清單）。",
            "- 不要泛泛說「多加內鏈」，要給出可直接套用的錨文字與連結位置。",
        ]
    else:
        lines += [
            "- 內容需直接修補上述缺口，不要泛泛寫新文章。",
            "- 若涉及 metadata，請一併產出 title、meta description、H1 草案。",
        ]
    return "\n".join(lines)
