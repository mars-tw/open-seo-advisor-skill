"""cloaking.check_referrer_based_redirect 測試：比較無 Referer 與帶有
Google 搜尋結果 Referer 時的最終導向網址，偵測 doorway page / 惡意重導
手法。外部網域重導給高 severity，同網域內路徑差異給低 severity/低信心。"""

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
def test_identical_destination_produces_no_findings():
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text="<html><body>Same for everyone</body></html>")
    )

    findings = cloaking.check_referrer_based_redirect("https://example.com/", _next_id_factory())
    assert findings == []


@respx.mock
def test_redirect_to_external_domain_only_with_search_referrer_flagged_high():
    """只有帶搜尋引擎 Referer 時才被導向外部網域——這是 doorway page 的
    典型手法，應該給高 severity。"""

    def _responder(request):
        referer = request.headers.get("referer", "")
        if "google.com/search" in referer:
            return httpx.Response(302, headers={"location": "https://scam-site.example/"})
        return httpx.Response(200, text="<html><body>Normal content</body></html>")

    respx.get("https://example.com/").mock(side_effect=_responder)
    respx.get("https://scam-site.example/").mock(
        return_value=httpx.Response(200, text="<html><body>scam</body></html>")
    )

    findings = cloaking.check_referrer_based_redirect("https://example.com/", _next_id_factory())
    assert len(findings) == 1
    assert findings[0].category == "malicious_redirect"
    assert findings[0].severity.value == "S1"
    assert "scam-site.example" in findings[0].evidence["referrer_final_url"]


@respx.mock
def test_redirect_to_same_domain_different_path_flagged_low():
    """帶搜尋引擎 Referer 時被導向同網域內的不同路徑（例如個人化到期活動頁）
    ——保守判斷，不斷言惡意，只給低 severity 提示。"""

    def _responder(request):
        referer = request.headers.get("referer", "")
        if "google.com/search" in referer:
            return httpx.Response(302, headers={"location": "https://example.com/campaign"})
        return httpx.Response(200, text="<html><body>Normal content</body></html>")

    respx.get("https://example.com/").mock(side_effect=_responder)
    respx.get("https://example.com/campaign").mock(
        return_value=httpx.Response(200, text="<html><body>campaign</body></html>")
    )

    findings = cloaking.check_referrer_based_redirect("https://example.com/", _next_id_factory())
    assert len(findings) == 1
    assert findings[0].severity.value == "S3"
    assert findings[0].confidence <= 0.3


@respx.mock
def test_fetch_failure_produces_no_findings_instead_of_raising():
    respx.get("https://example.com/").mock(return_value=httpx.Response(500))

    findings = cloaking.check_referrer_based_redirect("https://example.com/", _next_id_factory())
    assert findings == []


@respx.mock
def test_does_not_send_arbitrary_referer_value():
    """只固定使用 Google 搜尋結果 Referer，不提供任何自訂 Referer 的能力
    ——驗證發送的 Referer header 值固定，不受呼叫端影響。"""
    seen_referers = []

    def _responder(request):
        seen_referers.append(request.headers.get("referer", ""))
        return httpx.Response(200, text="<html><body>ok</body></html>")

    respx.get("https://example.com/").mock(side_effect=_responder)

    cloaking.check_referrer_based_redirect("https://example.com/", _next_id_factory())

    assert "" in seen_referers  # baseline：無 referer
    assert any("google.com/search" in r for r in seen_referers)
    assert all(r == "" or "google.com/search" in r for r in seen_referers)
