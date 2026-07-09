"""cloaking.check_cloaking 測試：比較一般 UA 與 Googlebot UA 的內容差異，
確認差異夠大才報 finding，且不斷言「一定是 cloaking」（confidence 偏低）。"""

from collections import Counter

import httpx
import respx

from seo_advisor.security_mode import cloaking


def _next_id_factory():
    counter: Counter[str] = Counter()

    def next_id(category: str) -> str:
        counter[category] += 1
        return f"SEC-{category.upper()}-{counter[category]:03d}"

    return next_id


@respx.mock
def test_identical_content_produces_no_findings():
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text="<html><body>Same content for everyone</body></html>",
                                     headers={"content-type": "text/html"})
    )

    findings = cloaking.check_cloaking("https://example.com/", _next_id_factory())
    assert findings == []


@respx.mock
def test_large_content_length_difference_flagged():
    call_count = {"n": 0}

    def _responder(request):
        call_count["n"] += 1
        ua = request.headers.get("user-agent", "")
        if "Googlebot" in ua:
            text = "<html><body>" + ("Rich detailed content. " * 200) + "</body></html>"
        else:
            text = "<html><body>Short.</body></html>"
        return httpx.Response(200, text=text, headers={"content-type": "text/html"})

    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/").mock(side_effect=_responder)

    findings = cloaking.check_cloaking("https://example.com/", _next_id_factory())
    content_findings = [f for f in findings if f.category == "cloaking" and "文字" in f.title]
    assert len(content_findings) == 1
    assert content_findings[0].confidence <= 0.5  # 不斷言一定是 cloaking


@respx.mock
def test_fetch_failure_produces_no_findings_instead_of_raising():
    """任一 UA 的請求失敗時，不該拋出例外中斷整個安全掃描，只是不比較。"""
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/").mock(return_value=httpx.Response(500))

    findings = cloaking.check_cloaking("https://example.com/", _next_id_factory())
    assert findings == []
