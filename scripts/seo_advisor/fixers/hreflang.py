"""hreflang 修復建議：只產出 plan_only=True 的建議方案，不自動寫入任何
檔案。

對應 analyzers/technical.py 的 `_check_hreflang` 產出的六種 Finding
（missing_self_reference/duplicate_language/invalid_code/non_reciprocal/
out_of_scope/mixed_implementation）。

刻意不做自動修復：hreflang 的正確性依賴語言/地區與網址的對應關係，這是
業務層面的資訊（例如 /en 對應哪個語言版本、是否真的有多語系版本），
crawler 無法從爬取結果安全地推斷或補全；自動插入錯誤的 hreflang 標籤
可能讓搜尋引擎誤判頁面對應關係，造成比不做更糟的 SEO 影響。因此只產出
具體的建議步驟，交由使用者依照網站實際的語言架構決定如何處理。
"""

from __future__ import annotations

from seo_advisor.fixers.models import PatchPlan
from seo_advisor.models import Finding

_HREFLANG_FINDING_MARKERS = (
    "HREFLANG_MISSING_SELF_REFERENCE",
    "HREFLANG_DUPLICATE_LANGUAGE",
    "HREFLANG_INVALID_CODE",
    "HREFLANG_NON_RECIPROCAL",
    "HREFLANG_OUT_OF_SCOPE",
    "HREFLANG_MIXED_IMPLEMENTATION",
)

_SUGGESTED_ACTIONS = {
    "HREFLANG_MISSING_SELF_REFERENCE": [
        "為每個受影響頁面補上一條指向自己的 hreflang alternate 標籤，"
        '例如：<link rel="alternate" hreflang="zh-TW" href="https://example.com/zh/page">'
        "（href 指向頁面自己的網址）。",
    ],
    "HREFLANG_DUPLICATE_LANGUAGE": [
        "檢查受影響頁面，確認每個語言/地區代碼只宣告一次 hreflang，"
        "移除重複的宣告並確認保留的那一條指向正確的目標網址。",
    ],
    "HREFLANG_INVALID_CODE": [
        "將格式不正確的 hreflang 代碼修正為 ISO 639-1 語言代碼（可選加 ISO "
        "3166-1 地區代碼），例如 zh-TW、en-US，或使用 x-default。",
    ],
    "HREFLANG_NON_RECIPROCAL": [
        "確認每一組互相參照的頁面都有對稱的 hreflang 宣告——如果 A 指向 B，"
        "B 也需要有一條指回 A 的 hreflang alternate 標籤。",
    ],
    "HREFLANG_OUT_OF_SCOPE": [
        "確認跨網域的 hreflang 目標是否為刻意設計的國際站群；如果不是，"
        "請修正為正確的網址。",
    ],
    "HREFLANG_MIXED_IMPLEMENTATION": [
        "決定只保留一種 hreflang 宣告形式（HTML <link> 標籤、HTTP header、"
        "或 sitemap 的 xhtml:link 三選一），移除其餘形式，避免兩處宣告"
        "不一致時難以排查問題。",
    ],
}


def can_fix(finding: Finding) -> bool:
    return any(marker in finding.id for marker in _HREFLANG_FINDING_MARKERS)


def plan_fix(finding: Finding) -> PatchPlan:
    """產出 hreflang 問題的建議方案（plan_only=True，不會實際寫入任何檔案）。"""
    marker = next(m for m in _HREFLANG_FINDING_MARKERS if m in finding.id)
    suggested_actions = list(_SUGGESTED_ACTIONS[marker])
    suggested_actions.append("套用建議後重新執行掃描，確認相同問題不再出現。")

    return PatchPlan(
        plan_id=f"fix-{finding.id}",
        finding_id=finding.id,
        fix_type="hreflang",
        risk_level="medium",
        targets=[],
        summary=(
            f"{finding.title}。hreflang 的正確性依賴語言/地區與網址的實際對應關係，"
            "這是業務層面的資訊，Engineer Mode 無法安全地自動推斷或修改，因此只"
            "產出建議，不會自動套用。"
        ),
        validation_steps=["套用建議後重新執行掃描，確認相同的 hreflang 問題不再出現"],
        warnings=[
            "這是建議方案，不是可自動套用的修復計畫；自動插入錯誤的 hreflang 可能"
            "讓搜尋引擎誤判頁面對應關係，請依照網站實際的語言架構手動處理。",
        ],
        plan_only=True,
        suggested_actions=suggested_actions,
    )
