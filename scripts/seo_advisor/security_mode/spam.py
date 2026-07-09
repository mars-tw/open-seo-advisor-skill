"""SEO spam 跡象偵測：隱藏文字/連結、與 Google 垃圾內容政策相符的可疑模式。

只用 HTML/CSS 層級的靜態特徵判斷，不做任何主動行為（不點擊、不執行 JS）。
這類特徵天生容易誤判（合理的無障礙設計也可能用 CSS 隱藏元素），因此一律標
confidence=medium 以下，並在 recommendation 提醒需人工複核，不斷言「一定是
被駭」。
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from seo_advisor.security_mode.models import SecurityFinding, SecuritySeverity, SeoImpact

_HIDDEN_STYLE_PATTERN = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|"
    r"font-size\s*:\s*0|text-indent\s*:\s*-9999px|opacity\s*:\s*0\b",
    re.IGNORECASE,
)

# 常見的垃圾內容注入關鍵詞（英文，粗略偵測，允許使用者網站本身合法涉及
# 這些主題時有較高誤判——因此只在「大量隱藏連結」同時出現才提高信心）。
_SUSPICIOUS_KEYWORDS = (
    "viagra", "cialis", "casino", "porn", "replica watch", "payday loan",
)


def check_seo_spam(html: str, url: str, next_id) -> list[SecurityFinding]:
    if not html:
        return []

    soup = BeautifulSoup(html, "lxml")
    findings: list[SecurityFinding] = []

    hidden_links = []
    for tag in soup.find_all(["a", "div", "span"]):
        style = tag.get("style", "")
        if style and _HIDDEN_STYLE_PATTERN.search(style):
            text = tag.get_text(strip=True)
            if text:
                hidden_links.append(text[:80])

    if hidden_links:
        suspicious_hits = sum(
            1 for text in hidden_links if any(kw in text.lower() for kw in _SUSPICIOUS_KEYWORDS)
        )
        confidence = 0.6 if suspicious_hits else 0.3
        findings.append(
            SecurityFinding(
                id=next_id("hidden_content"),
                title=f"偵測到 {len(hidden_links)} 個以 CSS 隱藏的文字/連結元素",
                category="seo_spam",
                severity=SecuritySeverity.S1_HIGH if suspicious_hits else SecuritySeverity.S2_MEDIUM,
                seo_impact=SeoImpact.RANKING,
                confidence=confidence,
                affected_urls=[url],
                evidence={"hidden_element_count": len(hidden_links), "sample": hidden_links[:5]},
                recommendation=(
                    "頁面含有以 CSS 隱藏（display:none/visibility:hidden/文字縮到極小等）的內容，"
                    "這可能是被駭入注入的垃圾連結，也可能是合理的無障礙設計（例如螢幕閱讀器專用文字），"
                    "請人工確認這些內容是否為你自己加入的。若非你所加入，網站可能已被入侵，"
                    "請立即檢查 CMS 帳號/外掛是否遭竄改並更換密碼。"
                ),
                needs_credential_rotation=bool(suspicious_hits),
            )
        )

    return findings
