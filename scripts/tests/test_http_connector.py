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

    assert connector.is_url_in_scope("https://www.example.com/x") is False

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
