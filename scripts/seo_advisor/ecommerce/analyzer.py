"""純邏輯的電商 listing 分析器。

對照 knowledge「ecommerce」領域的中性化方法論原則，做程式可判斷的檢核，
產出 Finding 與 listing 健康分數。資訊不足的欄位不硬給 finding。
"""

from __future__ import annotations

import re
from collections import Counter

from seo_advisor.ecommerce.models import EcommerceFinding, EcommerceListing, EcommerceReport
from seo_advisor.models import Severity

_CHECKLIST = {
    "title_frontload": "標題前段應放入核心品類、主要關鍵字與關鍵差異點。",
    "title_no_stuffing": "標題不要堆疊重複關鍵字，需兼顧搜尋與可讀性。",
    "bullets_value": "五點賣點每點只講一個購買理由，並用痛點、功能、好處、證據表達。",
    "main_image": "主圖必須清楚呈現商品本體與主要配件。",
    "secondary_images": "副圖應覆蓋尺寸、材質、使用情境、比較、安裝或使用步驟。",
    "a_plus": "A+ 內容應補足信任、情境、比較與品牌故事，不只是重複上方資訊。",
    "backend_keywords": "後端關鍵字只放前台未涵蓋但相關的搜尋詞。",
    "reviews_qa": "評論與 QA 應作為 listing 改版依據，降低購買疑慮。",
    "availability": "庫存、價格、配送與購買入口會直接影響轉換。",
    "variations": "變體 listing 必須符合真實規格差異，避免混淆或合規風險。",
}

_SEVERITY_PENALTY = {
    Severity.P0: 25.0,
    Severity.P1: 12.0,
    Severity.P2: 5.0,
    Severity.P3: 2.0,
}


def analyze_listing(listing: EcommerceListing) -> EcommerceReport:
    findings: list[EcommerceFinding] = []
    applied = list(_CHECKLIST.values())

    findings.extend(_check_availability(listing))
    findings.extend(_check_title(listing))
    findings.extend(_check_bullets(listing))
    findings.extend(_check_images(listing))
    findings.extend(_check_a_plus(listing))
    findings.extend(_check_backend_keywords(listing))
    findings.extend(_check_reviews(listing))
    findings.extend(_check_variations(listing))

    score = _compute_score(findings)
    return EcommerceReport(
        listing_ref=_derive_listing_ref(listing),
        findings=findings,
        listing_health_score=score,
        summary=_summary(score, findings),
        applied_checklist=applied,
    )


def _check_availability(listing: EcommerceListing) -> list[EcommerceFinding]:
    findings: list[EcommerceFinding] = []
    if not listing.in_stock:
        findings.append(
            EcommerceFinding(
                category="availability",
                severity=Severity.P0,
                title="商品目前缺貨，會直接阻斷轉換",
                evidence={"in_stock": listing.in_stock, "check": _CHECKLIST["availability"]},
                recommendation="優先處理補貨、預購或替代商品導流；缺貨期間不建議加大廣告流量。",
            )
        )
    if not listing.has_buy_box:
        findings.append(
            EcommerceFinding(
                category="availability",
                severity=Severity.P1,
                title="缺少主要購買入口，可能大幅影響轉換",
                evidence={"has_buy_box": listing.has_buy_box, "check": _CHECKLIST["availability"]},
                recommendation="檢查價格、庫存、配送、帳戶狀態與競爭賣家，優先恢復可購買入口。",
            )
        )
    return findings


def _check_title(listing: EcommerceListing) -> list[EcommerceFinding]:
    title = listing.title.strip()
    if not title:
        return []

    findings: list[EcommerceFinding] = []
    title_len = len(title)
    if title_len < 40:
        findings.append(
            EcommerceFinding(
                category="title",
                severity=Severity.P2,
                title="標題偏短，可能未充分傳達品類與差異點",
                evidence={"title_length": title_len, "check": _CHECKLIST["title_frontload"]},
                recommendation="補上核心品類、主要規格、使用情境與關鍵差異，但避免堆疊重複詞。",
            )
        )
    elif title_len > 180:
        findings.append(
            EcommerceFinding(
                category="title",
                severity=Severity.P2,
                title="標題偏長，可能影響可讀性與手機版掃讀",
                evidence={"title_length": title_len, "check": _CHECKLIST["title_frontload"]},
                recommendation="縮短標題，保留前段核心關鍵字、品類、規格與最重要賣點。",
            )
        )

    repeated = _repeated_terms(title)
    if repeated:
        findings.append(
            EcommerceFinding(
                category="title",
                severity=Severity.P2,
                title="標題可能有關鍵字堆疊",
                evidence={"repeated_terms": repeated, "check": _CHECKLIST["title_no_stuffing"]},
                recommendation="移除重複詞，改用自然語句整合品類、用途、規格與差異化。",
            )
        )
    return findings


def _check_bullets(listing: EcommerceListing) -> list[EcommerceFinding]:
    bullets = [bullet.strip() for bullet in listing.bullet_points if bullet.strip()]
    findings: list[EcommerceFinding] = []

    if not bullets:
        return []

    if len(bullets) < 5:
        findings.append(
            EcommerceFinding(
                category="bullets",
                severity=Severity.P2,
                title="賣點 bullet points 少於 5 點",
                evidence={"bullet_count": len(bullets), "check": _CHECKLIST["bullets_value"]},
                recommendation="補齊 5 個主要購買理由，例如痛點、功能、材質、情境、保固或比較。",
            )
        )

    short_count = sum(1 for bullet in bullets if len(bullet) < 35)
    if short_count:
        findings.append(
            EcommerceFinding(
                category="bullets",
                severity=Severity.P3,
                title="部分 bullet points 過短，說服力可能不足",
                evidence={"short_bullet_count": short_count, "check": _CHECKLIST["bullets_value"]},
                recommendation="每點補上具體好處或證據，避免只列功能名詞。",
            )
        )
    return findings


def _check_images(listing: EcommerceListing) -> list[EcommerceFinding]:
    findings: list[EcommerceFinding] = []
    if not listing.main_image_present:
        findings.append(
            EcommerceFinding(
                category="images",
                severity=Severity.P1,
                title="缺少主圖，會嚴重影響點擊與信任",
                evidence={"main_image_present": False, "check": _CHECKLIST["main_image"]},
                recommendation="補上清楚呈現商品本體與主要配件的主圖，再評估其他圖像優化。",
            )
        )
    if listing.secondary_image_count < 4:
        findings.append(
            EcommerceFinding(
                category="images",
                severity=Severity.P2,
                title="副圖數量不足，可能無法回答購買疑慮",
                evidence={
                    "secondary_image_count": listing.secondary_image_count,
                    "check": _CHECKLIST["secondary_images"],
                },
                recommendation="至少補到 4 張副圖，涵蓋尺寸、材質、情境、比較或使用步驟。",
            )
        )
    return findings


def _check_a_plus(listing: EcommerceListing) -> list[EcommerceFinding]:
    if listing.has_a_plus_content:
        return []
    return [
        EcommerceFinding(
            category="images",
            severity=Severity.P3,
            title="缺少 A+ 內容，品牌信任與情境說明不足",
            evidence={"has_a_plus_content": False, "check": _CHECKLIST["a_plus"]},
            recommendation="規劃 A+ 區塊補充使用情境、比較表、品牌信任、保固與常見疑慮。",
        )
    ]


def _check_backend_keywords(listing: EcommerceListing) -> list[EcommerceFinding]:
    keywords = [kw.strip() for kw in listing.backend_keywords if kw.strip()]
    if not keywords:
        return []
    if len(keywords) < 5:
        return [
            EcommerceFinding(
                category="keywords",
                severity=Severity.P3,
                title="後端關鍵字偏少，可能漏掉相關搜尋詞",
                evidence={"keyword_count": len(keywords), "check": _CHECKLIST["backend_keywords"]},
                recommendation="補上前台未出現但高度相關的同義詞、用途詞與長尾詞，避免重複與無關詞。",
            )
        ]
    return []


def _check_reviews(listing: EcommerceListing) -> list[EcommerceFinding]:
    findings: list[EcommerceFinding] = []
    if listing.review_count < 10:
        findings.append(
            EcommerceFinding(
                category="reviews",
                severity=Severity.P2,
                title="評論數偏少，社會證明不足",
                evidence={"review_count": listing.review_count, "check": _CHECKLIST["reviews_qa"]},
                recommendation="整理售後體驗、QA 與包裝提醒，降低負評並提高自然評論累積機會。",
            )
        )
    if listing.rating is not None and listing.rating < 4.0:
        findings.append(
            EcommerceFinding(
                category="reviews",
                severity=Severity.P1,
                title="評分低於 4.0，可能明顯影響轉換",
                evidence={"rating": listing.rating, "check": _CHECKLIST["reviews_qa"]},
                recommendation="優先分析低星評論主因，修正商品、包裝、說明或客服流程後再加大流量。",
            )
        )
    return findings


def _check_variations(listing: EcommerceListing) -> list[EcommerceFinding]:
    if listing.variations_count > 30:
        return [
            EcommerceFinding(
                category="variations",
                severity=Severity.P2,
                title="變體數量偏多，可能造成選擇困難或管理風險",
                evidence={
                    "variations_count": listing.variations_count,
                    "check": _CHECKLIST["variations"],
                },
                recommendation="確認變體皆為真實規格差異，並檢查是否需要拆分過度混雜的選項。",
            )
        ]
    return []


def _compute_score(findings: list[EcommerceFinding]) -> float:
    score = 100.0
    for finding in findings:
        score -= _SEVERITY_PENALTY[finding.severity]
    return max(0.0, round(score, 1))


def _summary(score: float, findings: list[EcommerceFinding]) -> str:
    p0_p1 = sum(1 for finding in findings if finding.severity in {Severity.P0, Severity.P1})
    if not findings:
        return "本次可判斷的 listing 基礎項目未發現明顯問題，可進一步檢查流量與 PPC 成效。"
    return (
        f"本次 listing 健康分數為 {score}/100，共發現 {len(findings)} 項可改善處，"
        f"其中 {p0_p1} 項屬於高優先處理。建議先處理庫存、購買入口、主圖、評分等"
        "會直接影響轉換的問題，再優化標題、圖片、A+ 與後端關鍵字。"
    )


def _derive_listing_ref(listing: EcommerceListing) -> str:
    title = listing.title.strip()
    return title[:80] if title else "ecommerce-listing"


def _repeated_terms(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+|[一-鿿]{2,}", text.lower())
    ignored = {"and", "with", "for", "the", "a", "an"}
    counts = Counter(token for token in tokens if token not in ignored and len(token) >= 2)
    return [token for token, count in counts.items() if count >= 3][:10]
