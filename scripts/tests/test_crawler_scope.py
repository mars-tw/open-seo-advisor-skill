"""驗證爬蟲的「同站範圍判斷」不會漏爬 www↔apex 版本的頁面。

背景：HTTPConnector.is_url_in_scope 與 crawler._same_site 過去用精確字串
比對 netloc，若目標網站的 www/apex 兩個版本都能直接訪問、沒有互相 redirect
（例如首頁連到 https://www.example.com/about 但這條連結本身不是 redirect），
爬蟲會把同站頁面誤判為外部連結而漏爬。兩者現在都改用 url_utils.normalize_host
正規化後比較，這裡驗證整合行為。
"""

import httpx
import respx

from seo_advisor.connectors.http import HTTPConnector
from seo_advisor.crawler import _same_site, crawl_site


def test_same_site_treats_www_and_apex_as_identical():
    assert _same_site("example.com", "https://www.example.com/about") is True
    assert _same_site("www.example.com", "https://example.com/about") is True
    assert _same_site("example.com", "https://evil-external-site.com/x") is False


@respx.mock
def test_crawl_site_does_not_lose_www_linked_pages():
    """首頁（apex）連到 www 版本的內頁時，爬蟲不該把它當外部連結跳過。"""
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(
            200,
            text='<html><body><a href="https://www.example.com/about">About</a></body></html>',
            headers={"content-type": "text/html"},
        )
    )
    respx.get("https://www.example.com/about").mock(
        return_value=httpx.Response(200, text="<html><body>About us</body></html>",
                                     headers={"content-type": "text/html"})
    )

    connector = HTTPConnector("https://example.com")
    result = crawl_site(connector, seed_url="https://example.com", max_urls=10, max_depth=2)

    assert "https://www.example.com/about" in result.pages
    assert result.pages["https://www.example.com/about"].status_code == 200
