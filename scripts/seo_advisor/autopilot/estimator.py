"""成本/影響明細產生器：把各模組會花錢/寫入/發布的動作，彙整成白話 CostEstimate。

誠實原則：無法精確估的一律標 ESTIMATED 或 UNKNOWN，不假裝精確；mock 情境
金額為 0 並註明「示範，不會真的花錢」。
"""

from __future__ import annotations

from seo_advisor.autopilot.models import (
    CostCategory,
    CostEstimate,
    CostEstimateItem,
    EstimateConfidence,
    RiskLevel,
)


def build_cost_estimate(
    *,
    estimate_id: str,
    generated_at: str,
    plan_image_variants: int = 0,
    plan_content_pieces: int = 0,
    plan_ad_budget_delta_minor_units: int = 0,
    currency: str = "TWD",
    mock: bool = True,
) -> CostEstimate:
    items: list[CostEstimateItem] = []
    unknown: list[str] = []
    total_known = 0

    if plan_image_variants > 0:
        note = "示範模式，不會真的呼叫 API、不會產生費用。" if mock else "實際費用依 provider 計價，屬預估。"
        items.append(
            CostEstimateItem(
                action_id="image-generate",
                module="image_material",
                action_summary=f"產生 {plan_image_variants} 張圖像素材",
                category=CostCategory.API_USAGE,
                amount_minor_units=0 if mock else None,
                currency=currency if mock else None,
                token_estimate=None,
                unit_notes=note,
                confidence=EstimateConfidence.FIXED if mock else EstimateConfidence.ESTIMATED,
                risk_level=RiskLevel.LOW,
                reversible=True,
                rollback_summary="刪除產出的圖檔即可。",
                user_facing_explanation=(
                    f"會產生 {plan_image_variants} 張廣告/社群用圖。"
                    + ("（示範模式不花錢）" if mock else "（實際會用到產圖 API 費用，金額為預估）")
                ),
                execution_allowed_after_consent=True,
            )
        )
        if not mock:
            unknown.append("產圖 API 實際費用（依 provider 與圖片數量而定）")

    if plan_content_pieces > 0:
        note = "示範模式，不會真的呼叫 LLM。" if mock else "實際費用依 LLM token 用量，屬預估。"
        items.append(
            CostEstimateItem(
                action_id="content-generate",
                module="content_writer",
                action_summary=f"產生 {plan_content_pieces} 篇內容草稿",
                category=CostCategory.API_USAGE,
                amount_minor_units=0 if mock else None,
                currency=currency if mock else None,
                token_estimate=None if mock else plan_content_pieces * 4000,
                unit_notes=note,
                confidence=EstimateConfidence.FIXED if mock else EstimateConfidence.ESTIMATED,
                risk_level=RiskLevel.LOW,
                reversible=True,
                rollback_summary="刪除產出的草稿檔即可。",
                user_facing_explanation=(
                    f"會產生 {plan_content_pieces} 篇文章草稿。"
                    + ("（示範模式不花錢）" if mock else "（實際會用到 LLM token 費用，金額為預估）")
                ),
                execution_allowed_after_consent=True,
            )
        )
        if not mock:
            unknown.append("LLM 內容產出的實際費用（依模型與 token 用量而定）")

    if plan_ad_budget_delta_minor_units > 0:
        total_known += plan_ad_budget_delta_minor_units
        items.append(
            CostEstimateItem(
                action_id="ad-budget-adjust",
                module="meta_ads",
                action_summary="調整廣告預算",
                category=CostCategory.AD_SPEND,
                amount_minor_units=plan_ad_budget_delta_minor_units,
                currency=currency,
                confidence=EstimateConfidence.ESTIMATED,
                risk_level=RiskLevel.HIGH,
                reversible=True,
                rollback_summary="會記錄原本預算，可還原。",
                user_facing_explanation=(
                    f"廣告每日預算最多可能增加 {plan_ad_budget_delta_minor_units / 100:g} {currency}。"
                    "（這是動用真實預算的動作，預設仍只產計畫、不自動加碼）"
                ),
                # 增加預算屬高風險擴大花費，autopilot MVP 不自動執行，只列明細與計畫
                execution_allowed_after_consent=False,
            )
        )

    summary = _plain_summary(items, total_known, currency, unknown, mock)
    return CostEstimate(
        estimate_id=estimate_id,
        generated_at=generated_at,
        dry_run=True,
        total_known_minor_units=total_known,
        currency=currency,
        items=items,
        unknown_cost_items=unknown,
        max_authorized_minor_units=total_known if total_known > 0 else None,
        plain_language_summary=summary,
    )


def _plain_summary(items, total_known, currency, unknown, mock) -> str:
    if not items:
        return "這次不會有任何花錢、寫入或發布的動作，全部都是免費的分析與建議。"
    parts = [f"這次同意後，系統最多可能執行 {len(items)} 項需要留意的動作。"]
    if mock:
        parts.append("目前是示範模式，不會真的花任何錢。")
    elif total_known > 0:
        parts.append(f"其中已知最高授權成本約 {total_known / 100:g} {currency}。")
    if unknown:
        parts.append(f"另有 {len(unknown)} 項成本無法精確估算，這些只會產生計畫、不會自動執行。")
    return " ".join(parts)
