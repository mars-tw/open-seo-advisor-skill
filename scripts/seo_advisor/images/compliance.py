"""圖像素材合規前置檢查：在把 prompt 送給圖像生成 provider 之前，先用規則
攔截明顯違規的需求（冒用品牌/名人、誤導性廣告、醫療金融保證等）。

這是安全底線，寧可誤擋也不放行——因為產出的素材若用於廣告投放，違規內容
可能導致廣告被拒、帳號受罰，甚至法律責任。攔截到違規時直接拒絕，不送出
API 請求（也順便省下無謂的 API 花費）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (規則說明, 觸發用的關鍵字/樣式)
_FORBIDDEN_PATTERNS: list[tuple[str, list[str]]] = [
    (
        "冒用或仿造他人品牌、商標、logo",
        ["競品 logo", "冒用", "山寨", "仿冒", "counterfeit", "fake logo", "competitor logo"],
    ),
    (
        "未授權使用真人、名人或政治人物肖像",
        ["名人", "明星", "政治人物", "總統", "celebrity", "politician", "real person face"],
    ),
    (
        "誤導性的療效／獲利保證",
        [
            "保證賺",
            "穩賺",
            "包治",
            "根治",
            "100% 有效",
            "100%有效",
            "guaranteed profit",
            "cure ",
            "miracle cure",
        ],
    ),
    (
        "偽造平台介面、假通知或假新聞截圖",
        ["假通知", "假新聞", "偽造截圖", "fake notification", "fake news", "fake ui"],
    ),
    (
        "仿冒特定在世藝術家的風格",
        ["in the style of ", "模仿藝術家", "某藝術家風格"],
    ),
]


@dataclass
class ComplianceResult:
    allowed: bool
    violations: list[str]
    notes: list[str]


def check_image_prompt(prompt: str, *, negative_prompt: str | None = None) -> ComplianceResult:
    """檢查 prompt（與 negative_prompt）是否觸犯合規規則。"""
    haystack = (prompt + " " + (negative_prompt or "")).lower()
    violations: list[str] = []

    for rule_name, keywords in _FORBIDDEN_PATTERNS:
        for kw in keywords:
            if kw.lower() in haystack:
                violations.append(f"{rule_name}（偵測到：{kw.strip()}）")
                break

    notes = [
        "AI 生成的素材建議在使用時揭露為 AI 生成內容。",
        "廣告素材上架前建議由人工確認是否符合 Meta 廣告政策與當地法規。",
    ]
    return ComplianceResult(allowed=not violations, violations=violations, notes=notes)


def contains_sensitive_targeting(text: str) -> bool:
    """偵測是否暗示以敏感屬性（健康狀況、種族、性向等）鎖定或標籤使用者。"""
    patterns = [
        r"你是不是有.*(病|症|障礙)",
        r"(得了|患有).*(癌|愛滋|憂鬱|糖尿病)",
        r"針對.*(同性戀|種族|宗教)",
    ]
    return any(re.search(p, text) for p in patterns)
