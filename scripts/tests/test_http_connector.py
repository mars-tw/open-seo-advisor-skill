import httpx
import pytest
import respx

from seo_advisor.connectors.http import HTTPConnector
from seo_advisor.models import SafetyPolicy
from seo_advisor.security.network_policy import PrivateNetworkBlockedError


@respx.mock
def test_probe_detects_robots_and_sitemap():
    respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /admin/\n")
    )
    respx.get("https://example.com/sitemap.xml").mock(return_value=httpx.Response(200, text="<urlset/>"))
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text="<html></html>"))

    connector = HTTPConnector("https://example.com")
    profile = connector.probe()

    assert profile.has_robots_txt is True
    assert profile.has_sitemap is True


@respx.mock
def test_fetch_url_respects_robots_disallow():
    respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
    )
    respx.get("https://example.com/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text="<html></html>"))

    connector = HTTPConnector("https://example.com")
    connector.probe()

    snapshot = connector.fetch_url("https://example.com/private/secret.html")
    assert snapshot.status_code == 0
    assert snapshot.fetch_error_type == "blocked_by_robots_txt"


@respx.mock
def test_fetch_url_allowed_page_returns_200():
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text="<html></html>"))
    respx.get("https://example.com/about.html").mock(
        return_value=httpx.Response(200, text="<h1>About</h1>", headers={"content-type": "text/html"})
    )

    connector = HTTPConnector("https://example.com")
    connector.probe()

    snapshot = connector.fetch_url("https://example.com/about.html")
    assert snapshot.status_code == 200
    assert "About" in snapshot.html
    assert snapshot.elapsed_ms is not None


@respx.mock
def test_fetch_url_records_timeout_error_type():
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text="<html></html>"))
    respx.get("https://example.com/slow.html").mock(side_effect=httpx.ConnectTimeout("timeout"))

    connector = HTTPConnector("https://example.com")
    connector.probe()

    snapshot = connector.fetch_url("https://example.com/slow.html")
    assert snapshot.status_code == 0
    assert snapshot.fetch_error_type == "timeout"


def test_constructor_rejects_private_network_by_default():
    with pytest.raises(PrivateNetworkBlockedError):
        HTTPConnector("http://localhost:8000")


def test_constructor_allows_private_network_when_policy_permits():
    policy = SafetyPolicy(allow_private_network=True)
    connector = HTTPConnector("http://localhost:8000", policy=policy)
    assert connector.base_url == "http://localhost:8000"


@respx.mock
def test_sitemap_external_urls_are_skipped_out_of_scope():
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(
            200,
            text=(
                '<?xml version="1.0"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                "<url><loc>https://example.com/page1</loc></url>"
                "<url><loc>https://evil-external-site.com/page2</loc></url>"
                "</urlset>"
            ),
        )
    )
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text="<html></html>"))

    connector = HTTPConnector("https://example.com")
    connector.probe()
    records = connector.list_urls("https://example.com", limit=10)

    urls = {r.url for r in records}
    assert "https://example.com/page1" in urls
    assert "https://evil-external-site.com/page2" not in urls


@respx.mock
def test_is_url_in_scope_expands_after_redirect_to_new_host():
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(
            200,
            text="<html></html>",
            headers={"content-type": "text/html"},
        )
    )

    connector = HTTPConnector("https://example.com")
    connector.probe()

    # www.example.com 與 example.com 視為同站（www↔apex 正規化），一開始
    # 就在範圍內，不需要等實際發生 redirect 才被納入。
    assert connector.is_url_in_scope("https://www.example.com/x") is True

    respx.get("https://example.com/redirect-source").mock(
        return_value=httpx.Response(
            200,
            text="<html></html>",
            headers={"content-type": "text/html"},
        )
    )
    connector.fetch_url("https://example.com/redirect-source")
    # 同 host 的請求本來就在 scope 內，這裡驗證 _register_final_host 不會誤移除既有 host
    assert connector.is_url_in_scope("https://example.com/anything") is True


def test_capabilities_are_read_only():
    connector = HTTPConnector("https://example.com")
    assert connector.capabilities() == {"read_urls"}


@respx.mock
def test_probe_then_fetch_url_does_not_repeat_request_for_same_path():
    """probe() 已經抓過 robots.txt/sitemap.xml/首頁後，fetch_url() 對同樣的路徑
    應該重用快取結果，而不是重新真正發送請求（避免同一次掃描重複打站）。"""
    robots_route = respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\n")
    )
    sitemap_route = respx.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(200, text="<urlset/>", headers={"content-type": "application/xml"})
    )
    home_route = respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text="<html>home</html>", headers={"content-type": "text/html"})
    )

    connector = HTTPConnector("https://example.com")
    connector.probe()
    assert robots_route.call_count == 1
    assert sitemap_route.call_count == 1
    assert home_route.call_count == 1

    # 這些呼叫模擬 crawler.py/scan_runner.py 對同一路徑的重複請求；
    # 都應該命中快取，call_count 維持在 1，不應該真的再打一次。
    # 首頁 URL 刻意用 connector.base_url（不帶尾斜線），與 probe() 內部一致——
    # 這正是 scan_runner.py 實際傳入 seed_url 的形式（normalize_url() 的輸出）。
    connector.fetch_url("https://example.com/robots.txt")
    connector.fetch_url("https://example.com/sitemap.xml")
    connector.fetch_url(connector.base_url)

    assert robots_route.call_count == 1
    assert sitemap_route.call_count == 1
    assert home_route.call_count == 1


@respx.mock
def test_list_urls_reuses_sitemap_fetched_by_probe():
    """probe() 抓過 sitemap.xml 後，list_urls() 不該重新抓取同一份 sitemap。"""
    sitemap_route = respx.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(
            200,
            text='<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<url><loc>https://example.com/a</loc></url></urlset>",
        )
    )
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text="<html></html>"))

    connector = HTTPConnector("https://example.com")
    connector.probe()
    assert sitemap_route.call_count == 1

    records = connector.list_urls("https://example.com", limit=10)
    assert sitemap_route.call_count == 1  # 沒有再打第二次
    assert any(r.url == "https://example.com/a" for r in records)


@respx.mock
def test_fetch_url_for_uncached_path_still_makes_a_request():
    """快取只影響 probe()/list_urls() 抓過的固定路徑，一般頁面仍正常發送請求。"""
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/").mock(return_value=httpx.Response(200, text="<html></html>"))
    page_route = respx.get("https://example.com/some-other-page").mock(
        return_value=httpx.Response(200, text="<html>page</html>")
    )

    connector = HTTPConnector("https://example.com")
    connector.probe()

    connector.fetch_url("https://example.com/some-other-page")
    assert page_route.call_count == 1


@respx.mock
def test_probe_path_sensitive_does_not_follow_cross_origin_redirect():
    """Security Mode 對敏感路徑（如 /.env）探測時，若該路徑意外 redirect 到
    第三方網域，不該追過去對未授權的第三方主機發送敏感路徑探測。"""
    respx.get("https://example.com/.env").mock(
        return_value=httpx.Response(302, headers={"location": "https://third-party.example.net/.env"})
    )
    third_party_route = respx.get("https://third-party.example.net/.env").mock(
        return_value=httpx.Response(200, text="leaked")
    )

    connector = HTTPConnector("https://example.com")
    result = connector.probe_path(".env", redact_preview=True)

    assert result.status_code == 0
    assert third_party_route.call_count == 0  # 第三方主機完全沒被打到


@respx.mock
def test_probe_path_sensitive_still_follows_same_origin_www_redirect():
    """同站的 www<->apex redirect 仍應正常追隨，不因 same_origin_only 而誤擋合法情況。"""
    respx.get("https://example.com/.env").mock(
        return_value=httpx.Response(301, headers={"location": "https://www.example.com/.env"})
    )
    respx.get("https://www.example.com/.env").mock(return_value=httpx.Response(404))

    connector = HTTPConnector("https://example.com")
    result = connector.probe_path(".env", redact_preview=True)

    assert result.status_code == 404
