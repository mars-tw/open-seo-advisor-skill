"""純邏輯的 CRO（轉換率優化）檢查與 A/B 測試規劃。

有落地頁 HTML 時，檢查結構/CTA/表單/信任訊號/訊息一致性/速度提示；沒有
HTML 時退回通用 CRO 檢查清單。純邏輯，不需要外部 API；有 URL 時可搭配
Consultant 的 crawler 取得 HTML。
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from seo_advisor.growth.models import AbTestIdea, CroFinding, CroReport
from seo_advisor.models import Severity

_CTA_KEYWORDS = (
    "立即", "免費", "預約", "購買", "加入", "註冊", "下載", "索取", "聯絡", "開始",
    "試用", "了解", "報名", "buy", "start", "sign up", "contact", "download", "book",
)
_TRUST_KEYWORDS = (
    "客戶", "案例", "見證", "評價", "review", "testimonial", "trust", "保證", "認證",
    "媒體", "合作", "安全", "隱私", "退款", "成功案例",
)
_SPEED_HINTS = ("script", "iframe", "video", "img")


def analyze_landing_page(html: str | None, url: str) -> CroReport:
    if not html:
        return _planning_only_report(url)

    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    findings: list[CroFinding] = []

    findings.extend(_check_structure(soup))
    findings.extend(_check_cta(soup))
    findings.extend(_check_form(soup))
    findings.extend(_check_trust(text))
    findings.extend(_check_message_match(soup))
    findings.extend(_check_speed_hints(soup))

    findings = _ensure_finding_range(findings)
    return CroReport(
        landing_url=url,
        findings=findings,
        ab_test_ideas=_default_ab_tests(has_html=True),
        conversion_hypotheses=_conversion_hypotheses(),
    )


def _planning_only_report(url: str) -> CroReport:
    return CroReport(
        landing_url=url,
        findings=[
            CroFinding(
                category="structure",
                severity=Severity.P2,
                title="尚未提供頁面 HTML，先以通用 CRO 清單規劃",
                evidence="沒有可解析的 HTML。",
                recommendation="提供落地頁 HTML 或 URL 爬取結果後，可檢查 H1、CTA、表單與信任訊號。",
            ),
            CroFinding(
                category="cta",
                severity=Severity.P2,
                title="確認首屏是否有明確 CTA",
                recommendation="首屏應讓使用者在 5 秒內知道下一步，例如預約、試用、下載或購買。",
            ),
            CroFinding(
                category="form",
                severity=Severity.P2,
                title="檢查表單欄位是否過多",
                recommendation="冷流量表單先只收必要欄位，降低轉換阻力。",
            ),
        ],
        ab_test_ideas=_default_ab_tests(has_html=False),
        conversion_hypotheses=_conversion_hypotheses(),
    )


def _check_structure(soup: BeautifulSoup) -> list[CroFinding]:
    h1_tags = soup.find_all("h1")
    if not h1_tags:
        return [
            CroFinding(
                category="structure",
                severity=Severity.P1,
                title="頁面缺少明確 H1",
                evidence="未找到 <h1>。",
                recommendation="新增單一且清楚的 H1，直接說明這頁的核心承諾與目標受眾。",
            )
        ]
    if len(h1_tags) > 1:
        return [
            CroFinding(
                category="structure",
                severity=Severity.P3,
                title="頁面有多個 H1",
                evidence=f"找到 {len(h1_tags)} 個 H1。",
                recommendation="保留一個主 H1，其餘段落標題改用 H2/H3，讓訊息階層更清楚。",
            )
        ]
    return []


def _check_cta(soup: BeautifulSoup) -> list[CroFinding]:
    candidates = soup.find_all(["a", "button"])
    ctas = [node.get_text(" ", strip=True) for node in candidates]
    meaningful = [text for text in ctas if _looks_like_cta(text)]

    if not meaningful:
        return [
            CroFinding(
                category="cta",
                severity=Severity.P1,
                title="頁面缺少明確 CTA",
                evidence="未找到含行動語意的按鈕或連結。",
                recommendation="加入明確 CTA，例如「立即預約」、「免費試用」、「索取報價」。",
            )
        ]

    vague = [text for text in meaningful if text in {"了解更多", "more", "learn more"}]
    if len(vague) == len(meaningful):
        return [
            CroFinding(
                category="cta",
                severity=Severity.P2,
                title="CTA 文字偏模糊",
                evidence=f"目前 CTA：{', '.join(meaningful[:5])}",
                recommendation="把 CTA 改成具體行動與價值，例如「預約 30 分鐘諮詢」。",
            )
        ]
    return []


def _check_form(soup: BeautifulSoup) -> list[CroFinding]:
    forms = soup.find_all("form")
    if not forms:
        return [
            CroFinding(
                category="form",
                severity=Severity.P2,
                title="頁面未偵測到表單",
                evidence="未找到 <form>。",
                recommendation="若此頁目標是名單或詢問，應加入簡短表單或清楚的聯絡入口。",
            )
        ]

    findings: list[CroFinding] = []
    for form in forms:
        fields = form.find_all(["input", "select", "textarea"])
        visible_fields = [
            field for field in fields if field.get("type", "").lower() not in {"hidden", "submit"}
        ]
        if len(visible_fields) > 5:
            findings.append(
                CroFinding(
                    category="form",
                    severity=Severity.P2,
                    title="表單欄位可能過多",
                    evidence=f"偵測到 {len(visible_fields)} 個可填欄位。",
                    recommendation="先保留必要欄位，將非必要問題移到後續客服或銷售流程。",
                )
            )
            break
    return findings


def _check_trust(text: str) -> list[CroFinding]:
    lowered = text.lower()
    if not any(keyword.lower() in lowered for keyword in _TRUST_KEYWORDS):
        return [
            CroFinding(
                category="trust",
                severity=Severity.P2,
                title="頁面缺少明顯信任訊號",
                evidence="未偵測到案例、評價、認證、退款、安全或合作客戶等信任關鍵字。",
                recommendation="補上客戶案例、見證、合作品牌、認證或保證機制，降低轉換疑慮。",
            )
        ]
    return []


def _check_message_match(soup: BeautifulSoup) -> list[CroFinding]:
    title = _first_text(soup.find("title"))
    h1 = _first_text(soup.find("h1"))
    cta_texts = [
        node.get_text(" ", strip=True)
        for node in soup.find_all(["a", "button"])
        if _looks_like_cta(node.get_text(" ", strip=True))
    ]

    if title and h1 and _token_overlap(title, h1) < 0.2:
        return [
            CroFinding(
                category="message_match",
                severity=Severity.P2,
                title="Title 與 H1 訊息可能不一致",
                evidence=f"title={title}; h1={h1}",
                recommendation="讓廣告、搜尋結果標題、H1 與 CTA 使用一致承諾，避免使用者落地後困惑。",
            )
        ]

    if h1 and cta_texts and not any(_token_overlap(h1, cta) > 0 for cta in cta_texts):
        return [
            CroFinding(
                category="message_match",
                severity=Severity.P3,
                title="H1 與 CTA 關聯偏弱",
                evidence=f"h1={h1}; cta={', '.join(cta_texts[:3])}",
                recommendation="CTA 應呼應頁面主承諾，例如 H1 講試用，CTA 就明確引導開始試用。",
            )
        ]
    return []


def _check_speed_hints(soup: BeautifulSoup) -> list[CroFinding]:
    counts = {tag: len(soup.find_all(tag)) for tag in _SPEED_HINTS}
    heavy_score = counts["script"] + counts["iframe"] * 3 + counts["video"] * 3 + counts["img"]

    if heavy_score >= 40:
        return [
            CroFinding(
                category="speed_hint",
                severity=Severity.P2,
                title="頁面資源數量偏多，可能影響載入與轉換",
                evidence=", ".join(f"{key}={value}" for key, value in counts.items()),
                recommendation="檢查圖片壓縮、第三方 script、影片與 iframe，優先改善首屏載入速度。",
            )
        ]
    return []


def _default_ab_tests(*, has_html: bool) -> list[AbTestIdea]:
    ideas = [
        AbTestIdea(
            element="首屏標題",
            hypothesis="更具體的價值承諾能提升使用者繼續閱讀與點擊 CTA 的比例。",
            variant_a="目前標題",
            variant_b="加入目標受眾與可量化結果的標題",
            primary_metric="CTA click-through rate",
            min_sample_hint="每組至少累積 300-500 次有效訪問後再初步判讀。",
        ),
        AbTestIdea(
            element="CTA 文字",
            hypothesis="具體行動型 CTA 比模糊 CTA 更容易提升轉換。",
            variant_a="了解更多",
            variant_b="預約免費諮詢",
            primary_metric="form submit rate",
            min_sample_hint="每組至少 50 次 CTA 點擊或 20 次轉換後再比較。",
        ),
        AbTestIdea(
            element="信任訊號",
            hypothesis="在 CTA 附近加入案例或評價能降低疑慮並提升表單送出率。",
            variant_a="無信任訊號",
            variant_b="CTA 附近加入客戶見證或合作品牌",
            primary_metric="conversion rate",
            min_sample_hint="至少跑滿一個完整週間週期，避免日別流量偏差。",
        ),
    ]
    if has_html:
        ideas.append(
            AbTestIdea(
                element="表單欄位",
                hypothesis="減少非必要欄位能降低填寫阻力。",
                variant_a="目前表單",
                variant_b="只保留姓名、聯絡方式與主要需求",
                primary_metric="form completion rate",
                min_sample_hint="每組至少 100 次表單開始填寫後再觀察完成率。",
            )
        )
    return ideas[:4]


def _conversion_hypotheses() -> list[str]:
    return [
        "若首屏承諾更清楚，CTA 點擊率應提升。",
        "若表單阻力降低，表單完成率應提升。",
        "若信任訊號更靠近 CTA，冷流量轉換率應提升。",
        "若廣告訊息、H1 與 CTA 一致，跳出率應下降。",
    ]


def _ensure_finding_range(findings: list[CroFinding]) -> list[CroFinding]:
    if len(findings) < 3:
        findings.extend(
            [
                CroFinding(
                    category="cta",
                    severity=Severity.P3,
                    title="建議檢查 CTA 是否在首屏可見",
                    recommendation="確保使用者不用捲動太久就能看到下一步行動。",
                ),
                CroFinding(
                    category="trust",
                    severity=Severity.P3,
                    title="建議把信任訊號放到決策點附近",
                    recommendation="在價格、表單或 CTA 附近放置案例、評價或保證說明。",
                ),
                CroFinding(
                    category="message_match",
                    severity=Severity.P3,
                    title="建議比對廣告文案與落地頁承諾",
                    recommendation="廣告吸引使用者的承諾，落地頁首屏必須立即接住。",
                ),
            ]
        )
    return findings[:6]


def _looks_like_cta(text: str) -> bool:
    normalized = text.strip().lower()
    return bool(normalized) and any(keyword in normalized for keyword in _CTA_KEYWORDS)


def _first_text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _token_overlap(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), 1)


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+|[一-鿿]", text.lower()))
