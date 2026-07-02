"""把 docs/content_writer_guide.md 的 10 條核心原則中，能用程式邏輯直接檢查
的部分實作出來。程式檢查負責「結構性、可驗證」的規則，例如：

- 是否只有一個 H1
- 是否有明確標示「需要查證」的不確定內容
- 是否包含常見的低品質 AI 內容起手式（空泛開場白）
- YMYL 關鍵字是否命中，若命中則強制要求人工審查

「內容是否真的有洞察、經驗是否可信、語氣是否在地化」這類需要語意理解的
判斷，交給 LLM QA 階段自我檢查（見 pipeline.py 的 QA 步驟），這裡不重複
實作。這個模組的結果會併入 QA 階段的 EditorialIssue 清單，而不是取代它。
"""

from __future__ import annotations

import re

from seo_advisor.writers.models import EditorialIssue

_YMYL_KEYWORDS = [
    "醫療",
    "診斷",
    "治療",
    "藥物",
    "手術",
    "投資",
    "貸款",
    "保險",
    "法律",
    "訴訟",
    "稅務",
    "醫生",
    "健康",
    "financial advice",
    "medical",
    "diagnosis",
    "treatment",
    "investment",
    "legal advice",
]

_LOW_QUALITY_OPENERS = [
    "在當今快速變化的世界中",
    "隨著科技的進步",
    "在這個數位時代",
    "眾所周知",
    "不可否認",
    "in today's fast-paced world",
    "in this digital age",
]

_NEEDS_VERIFICATION_MARKER = "[需要查證"


def check_single_h1(markdown: str) -> EditorialIssue | None:
    h1_count = len(re.findall(r"^#\s+.+$", markdown, flags=re.MULTILINE))
    if h1_count == 0:
        return EditorialIssue(
            category="structure",
            severity="P1",
            description="草稿沒有任何 H1（一級標題）。",
            recommendation="為文章加上一個能反映主題的 H1 標題。",
        )
    if h1_count > 1:
        return EditorialIssue(
            category="structure",
            severity="P2",
            description=f"草稿有 {h1_count} 個 H1，應該只有一個。",
            recommendation="把多餘的 H1 降級為 H2 或 H3，保持單一主標題的階層結構。",
        )
    return None


def check_low_quality_openers(markdown: str) -> EditorialIssue | None:
    lowered = markdown.lower()
    hits = [phrase for phrase in _LOW_QUALITY_OPENERS if phrase.lower() in lowered]
    if hits:
        return EditorialIssue(
            category="content_quality",
            severity="P2",
            description=f"草稿包含常見的低品質 AI 內容起手式：{', '.join(hits)}",
            recommendation="改寫開頭，直接切入讀者真正關心的問題，避免空泛的場景鋪陳。",
        )
    return None


def check_ymyl_keywords(markdown: str) -> EditorialIssue | None:
    lowered = markdown.lower()
    hits = [kw for kw in _YMYL_KEYWORDS if kw.lower() in lowered]
    if hits:
        return EditorialIssue(
            category="trust",
            severity="P1",
            description=(
                f"草稿內容命中 YMYL（Your Money or Your Life）相關關鍵字：{', '.join(hits)}"
            ),
            recommendation="這類主題（健康/財務/法律/人身安全）建議由領域專家審核後才能發布，"
            "不應單獨作為最終內容使用。",
        )
    return None


def count_verification_markers(markdown: str) -> int:
    """統計草稿中標示「需要查證」的次數，用於報告透明度，不視為錯誤本身。"""
    return markdown.count(_NEEDS_VERIFICATION_MARKER)


def run_structural_checks(markdown: str) -> list[EditorialIssue]:
    """執行所有可程式化檢查的規則，回傳發現的問題清單（可能是空清單）。"""
    checks = [check_single_h1, check_low_quality_openers, check_ymyl_keywords]
    issues = []
    for check in checks:
        result = check(markdown)
        if result is not None:
            issues.append(result)
    return issues
