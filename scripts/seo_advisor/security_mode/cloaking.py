"""Cloaking 粗略偵測：比較一般瀏覽器 UA 與 Googlebot/行動裝置 UA 拿到的內容
是否有明顯差異；以及比較有無「來自 Google 搜尋結果」的 Referer 時，最終
導向網址是否不同（常見的 doorway page / 惡意重導手法：直接訪問顯示正常
內容，偵測到搜尋引擎 referrer 才導向詐騙/垃圾內容，藉此在人工審查或
Google 重新抓取時——通常沒有這個 referrer——躲過偵測）。

刻意只做「比較」，不提供任何繞過限速、繞過封鎖、代理、cookie replay、
自訂 header 的能力——每個 UA/Referer 組合各自透過獨立的 HTTPConnector
實例發送請求，與一般頁面爬取套用同一套 SSRF 防護，只是切換 User-Agent
或 Referer 字串本身（這與很多正當的 SEO 稽核工具做法一致，且 UA 差異
本來就是 Googlebot 自己在網路上公開會用的字串，Referer 也只固定使用
`https://www.google.com/search?...` 這組公開、無害的字串，不構成繞過任何
限制、不提供任意自訂 Referer 的能力）。所有 connector 共用同一個
RateLimiter 實例（見各 check_* 函式的 rate_limiter 參數），確保「對同一個
目標網站的總請求速率」不會因為多開 connector 而被稀釋掉。

差異天生可能來自響應式設計、A/B 測試、CDN 快取、個人化內容，而不是真的
cloaking 或惡意重導，因此一律標保守的 confidence，不斷言「這確實是惡意
行為」，只在「導向外部網域」這種明確訊號時才給較高的 severity。
"""

from __future__ import annotations

from urllib.parse import urlparse

from bs4 import BeautifulSoup

from seo_advisor.connectors.http import HTTPConnector
from seo_advisor.models import SafetyPolicy
from seo_advisor.security.rate_limiter import RateLimiter
from seo_advisor.security_mode.models import SecurityFinding, SecuritySeverity, SeoImpact
from seo_advisor.url_utils import normalize_host

_GOOGLEBOT_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
_MOBILE_UA = "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36"
_DEFAULT_UA = "OpenSEOAdvisor/0.1 (SecurityAudit)"

# 固定使用這組公開、無害的 Referer 字串模擬「使用者從 Google 搜尋結果點擊
# 進來」，不提供任何自訂 Referer 的能力（那等於變成通用的 header injection
# 工具，超出被動式稽核的範圍）。
_GOOGLE_SEARCH_REFERRER = "https://www.google.com/search?q=site"

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


def _fetch_with_referer(
    url: str, *, referer: str | None, rate_limiter: RateLimiter
) -> tuple[int, str, str]:
    """與 _fetch_with_ua 相同，但可額外指定 Referer header（僅限固定的
    _GOOGLE_SEARCH_REFERRER 常數，不對外開放任意值）；User-Agent 固定使用
    一般瀏覽器字串，只有 Referer 這一個變因不同，確保比較的是「Referer
    造成的差異」而非同時混雜 UA 差異。"""
    connector = HTTPConnector(
        url,
        user_agent=_DEFAULT_UA,
        policy=SafetyPolicy(allowed_capabilities={"read_urls"}),
        rate_limiter=rate_limiter,
        extra_headers={"Referer": referer} if referer else None,
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


def check_referrer_based_redirect(
    url: str, next_id, *, rate_limiter: RateLimiter | None = None
) -> list[SecurityFinding]:
    """比較「無 Referer」與「帶有 Google 搜尋結果 Referer」兩種情境下的最終
    導向網址，偵測常見的 doorway page / 惡意重導手法：直接訪問時顯示正常
    內容，只有偵測到使用者從搜尋引擎點擊進來（有對應的 Referer header）才
    導向詐騙/垃圾內容——這種手法會在人工審查、Google 自己重新抓取時
    （通常沒有這個 referrer）躲過偵測，但一般使用者從搜尋結果點擊進來時
    仍會受害。

    判斷保守：只有在「導向外部網域」或「狀態碼從可正常存取變成 3xx 到
    外部網域」這種明確訊號時才給較高 severity；同網域內的路徑差異或純
    內容差異可能只是個人化/A-B 測試/CDN 快取造成，維持低 severity 並在
    文案裡說明這個可能性，不斷言「這確實是惡意行為」。
    """
    shared_rate_limiter = rate_limiter or RateLimiter(3.0)
    baseline_status, baseline_final, baseline_text = _fetch_with_referer(
        url, referer=None, rate_limiter=shared_rate_limiter
    )
    referrer_status, referrer_final, referrer_text = _fetch_with_referer(
        url, referer=_GOOGLE_SEARCH_REFERRER, rate_limiter=shared_rate_limiter
    )

    if not baseline_final or not referrer_final:
        return []  # 任一請求失敗，無法比較，不產生發現（避免誤判）

    if baseline_final == referrer_final:
        return []

    baseline_host = normalize_host(urlparse(baseline_final).netloc)
    referrer_host = normalize_host(urlparse(referrer_final).netloc)
    redirected_to_external = baseline_host != referrer_host

    findings: list[SecurityFinding] = []

    if redirected_to_external:
        findings.append(
            SecurityFinding(
                id=next_id("referrer_redirect_external"),
                title="偵測到「來自搜尋引擎點擊」時被導向不同網域，可能是惡意重導",
                category="malicious_redirect",
                severity=SecuritySeverity.S1_HIGH,
                seo_impact=SeoImpact.USER_SAFETY,
                confidence=0.5,
                affected_urls=[url],
                evidence={
                    "baseline_final_url": baseline_final,
                    "referrer_final_url": referrer_final,
                    "referrer_used": _GOOGLE_SEARCH_REFERRER,
                },
                recommendation=(
                    "直接訪問這個網址與帶有 Google 搜尋結果 Referer 訪問時，被導向了不同的網域。"
                    "這是常見的惡意重導/doorway page 手法：只在偵測到使用者從搜尋引擎點擊進來時"
                    "才導向詐騙或垃圾內容，藉此在人工審查時躲過偵測。請立即人工確認這個網站是否"
                    "遭到入侵（檢查 .htaccess、外掛、主題檔案是否被植入可疑重導程式碼），"
                    "如果是刻意的行銷追蹤重導請忽略此提示。"
                    "（此檢查只固定使用一組搜尋結果 Referer 測試，無法涵蓋只針對特定關鍵字/"
                    "URL 才觸發的條件式重導，未觸發不代表網站完全沒有這類問題。）"
                ),
            )
        )
    else:
        findings.append(
            SecurityFinding(
                id=next_id("referrer_redirect_same_site"),
                title="偵測到「來自搜尋引擎點擊」時導向了同網域內的不同路徑",
                category="malicious_redirect",
                severity=SecuritySeverity.S3_LOW,
                seo_impact=SeoImpact.TRUST,
                confidence=0.2,
                affected_urls=[url],
                evidence={"baseline_final_url": baseline_final, "referrer_final_url": referrer_final},
                recommendation=(
                    "直接訪問與帶有搜尋引擎 Referer 訪問時導向了同網域內的不同路徑，"
                    "這通常是合理的行為（例如個人化內容、A/B 測試、活動追蹤頁），"
                    "但也建議人工確認這不是非預期的重導設定。"
                ),
            )
        )

    return findings
