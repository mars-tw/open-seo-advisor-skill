"""Cloaking 粗略偵測：比較一般瀏覽器 UA 與 Googlebot/行動裝置 UA 拿到的內容
是否有明顯差異。

刻意只做「比較」，不提供任何繞過限速、繞過封鎖、代理、cookie replay、
自訂 header 的能力——每個 UA 各自透過獨立的 HTTPConnector 實例發送請求，
與一般頁面爬取套用同一套 SSRF 防護，只是切換 User-Agent 字串本身（這與
很多正當的 SEO 稽核工具做法一致，且 UA 差異本來就是 Googlebot 自己在
網路上公開會用的字串，不構成繞過任何限制）。兩個 connector 共用同一個
RateLimiter 實例（見 check_cloaking 的 rate_limiter 參數），確保「對同一個
目標網站的總請求速率」不會因為多開一個 connector 而被稀釋掉。

差異天生可能來自響應式設計、A/B 測試、CDN 快取，而不是真的 cloaking，
因此一律標 confidence=medium 以下，不斷言「這是 cloaking」。
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from seo_advisor.connectors.http import HTTPConnector
from seo_advisor.models import SafetyPolicy
from seo_advisor.security.rate_limiter import RateLimiter
from seo_advisor.security_mode.models import SecurityFinding, SecuritySeverity, SeoImpact

_GOOGLEBOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
_MOBILE_UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36"

# 主要文字內容長度差異超過這個比例才視為「可能有差異」，避免因為極小幅度的
# 動態內容（廣告、時間戳記）就誤判。
_TEXT_LENGTH_DIFF_THRESHOLD = 0.4


def _fetch_with_ua(url: str, user_agent: str, rate_limiter: RateLimiter) -> tuple[int, str, str]:
    """回傳 (status_code, final_url, 主要文字內容)。任何錯誤都回傳空字串，
    呼叫端據此判斷跳過比較，不拋出例外中斷整個安全掃描。"""
    connector = HTTPConnector(
        url,
        user_agent=user_agent,
        policy=SafetyPolicy(allowed_capabilities={"read_urls"}),
        rate_limiter=rate_limiter,
    )
    try:
        snapshot = connector.fetch_url(url, fetched_at="")
        text = ""
        if snapshot.html:
            text = BeautifulSoup(snapshot.html, "lxml").get_text(separator=" ", strip=True)
        return snapshot.status_code, snapshot.final_url, text
    finally:
        connector.close()


def check_cloaking(url: str, next_id, *, rate_limiter: RateLimiter | None = None) -> list[SecurityFinding]:
    shared_rate_limiter = rate_limiter or RateLimiter(3.0)
    normal_status, normal_final, normal_text = _fetch_with_ua(
        url, "OpenSEOAdvisor/0.1 (SecurityAudit)", shared_rate_limiter
    )
    bot_status, bot_final, bot_text = _fetch_with_ua(url, _GOOGLEBOT_UA, shared_rate_limiter)

    if not normal_text or not bot_text:
        return []  # 任一請求失敗，無法比較，不產生發現（避免誤判）

    findings: list[SecurityFinding] = []

    if normal_final != bot_final:
        findings.append(
            SecurityFinding(
                id=next_id("cloaking_redirect"),
                title="一般瀏覽器與 Googlebot 的最終導向網址不同",
                category="cloaking",
                severity=SecuritySeverity.S2_MEDIUM,
                seo_impact=SeoImpact.TRUST,
                confidence=0.4,
                affected_urls=[url],
                evidence={"normal_final_url": normal_final, "googlebot_final_url": bot_final},
                recommendation=(
                    "一般使用者與 Googlebot 被導向不同的最終網址，這可能是合理的（例如地區/裝置導向），"
                    "也可能是 cloaking 或惡意重導，請人工確認這個差異是否為你刻意設計的行為。"
                ),
            )
        )

    len_diff = abs(len(normal_text) - len(bot_text)) / max(len(normal_text), len(bot_text), 1)
    if len_diff > _TEXT_LENGTH_DIFF_THRESHOLD:
        findings.append(
            SecurityFinding(
                id=next_id("cloaking_content"),
                title="一般瀏覽器與 Googlebot 看到的主要文字內容長度差異顯著",
                category="cloaking",
                severity=SecuritySeverity.S2_MEDIUM,
                seo_impact=SeoImpact.RANKING,
                confidence=0.3,
                affected_urls=[url],
                evidence={
                    "normal_text_length": len(normal_text),
                    "googlebot_text_length": len(bot_text),
                    "diff_ratio": round(len_diff, 2),
                },
                recommendation=(
                    "兩種 User-Agent 拿到的頁面文字內容長度差異較大，可能是響應式設計/A-B 測試造成，"
                    "也可能是對搜尋引擎顯示不同內容（cloaking），建議人工比對實際內容差異。"
                ),
            )
        )

    return findings
