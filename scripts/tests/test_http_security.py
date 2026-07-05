"""HTTPConnector 的資安/資源防護測試：SSRF redirect 繞過、回應大小上限。"""

import httpx

from seo_advisor.models import PageSnapshot


def _connector_with_transport(handler):
    """建立一個 HTTPConnector，並把它的 client 換成用 MockTransport 的 client，
    這樣就能在不連真網路的情況下模擬 redirect / 各種回應。"""
    from seo_advisor.connectors.http import HTTPConnector

    conn = HTTPConnector("https://example.com")
    conn._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,  # 與正式一致：由 _safe_get 手動追
    )
    return conn


def test_redirect_to_private_ip_is_blocked():
    """公開網址 302 轉到雲端 metadata IP 時，必須被 SSRF 防護擋下。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
        # 若真的走到 metadata，回傳機密內容——測試要確保永遠走不到這裡
        return httpx.Response(200, text="SECRET-METADATA")

    conn = _connector_with_transport(handler)
    snap: PageSnapshot = conn.fetch_url("https://example.com/go", fetched_at="t")
    conn.close()

    assert snap.status_code == 0
    assert snap.fetch_error_type == "private_network_blocked"
    assert "SECRET-METADATA" not in snap.html


def test_redirect_to_disallowed_scheme_is_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "file:///etc/passwd"})

    conn = _connector_with_transport(handler)
    snap = conn.fetch_url("https://example.com/x", fetched_at="t")
    conn.close()
    # file:// scheme 被擋，回報為一般 HTTP 錯誤（非成功）
    assert snap.status_code == 0
    assert snap.html == ""


def test_normal_redirect_still_works():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "https://example.com/new"})
        return httpx.Response(200, text="<html>ok</html>", headers={"content-type": "text/html"})

    conn = _connector_with_transport(handler)
    snap = conn.fetch_url("https://example.com/old", fetched_at="t")
    conn.close()
    assert snap.status_code == 200
    assert "ok" in snap.html
    assert snap.redirect_chain  # 有記錄到 redirect 歷程


def test_oversized_content_length_returns_empty_body():
    """content-length 宣告超過上限時，body 不下載、html 為空。"""
    from seo_advisor.connectors.http import _MAX_HTML_BYTES

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "content-length": str(_MAX_HTML_BYTES + 1),
                "content-type": "text/html",
            },
            text="<html>should-not-be-read</html>",
        )

    conn = _connector_with_transport(handler)
    snap = conn.fetch_url("https://example.com/big", fetched_at="t")
    conn.close()
    assert snap.html == ""


def test_streaming_truncates_oversized_body():
    """實際 body 超過上限時（header 沒說），串流會在超限時截斷成空，不 OOM。"""
    from seo_advisor.connectors.http import _MAX_HTML_BYTES

    big = "a" * (_MAX_HTML_BYTES + 1000)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=big, headers={"content-type": "text/html"})

    conn = _connector_with_transport(handler)
    snap = conn.fetch_url("https://example.com/big", fetched_at="t")
    conn.close()
    # 超過上限 → 視為不處理，回空（避免把超大內容留在記憶體/報告）
    assert snap.html == ""


def test_sitemap_with_doctype_is_rejected():
    """含 DOCTYPE 的 sitemap（可能是 billion laughs 攻擊）不予解析。"""
    xml = '<!DOCTYPE x [<!ENTITY a "aaa">]><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=xml, headers={"content-type": "application/xml"})

    conn = _connector_with_transport(handler)
    records = conn.list_urls("https://example.com", limit=10)
    conn.close()
    # 被拒解析後沒有 sitemap 記錄，只會退回 seed
    assert all(r.source != "sitemap" for r in records)
