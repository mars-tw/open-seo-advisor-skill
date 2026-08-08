"""驗證 robots.txt / sitemap.xml 這類「非 HTML 純文字資產」的內容不會在抓取時消失。

背景：`PageSnapshot.html` 只保留真正的 HTML，所以 `HTTPConnector.fetch_url()`
對非 `text/html` 的回應會回傳空字串。crawler 正是靠 `fetch_url()` 取得
robots.txt 與 sitemap.xml，於是網站**真的有**這兩個檔案時反而拿到空字串，
分析器接著誤判成「robots.txt 未宣告 sitemap」與「sitemap.xml 不是合法 XML」
（後者是 P1），造成補上檔案的網站分數比完全沒有時更低。

修法是讓純文字型回應把解碼後的內容放進 `headers["_raw_text"]`（crawler 原本
就在讀這個鍵），這裡鎖住整合行為避免再度回歸。
"""

import httpx
import respx

from seo_advisor.analyzers.technical import analyze_technical_seo
from seo_advisor.connectors.http import HTTPConnector
from seo_advisor.crawler import crawl_site

_ROBOTS = "User-agent: *\nAllow: /\n\nSitemap: https://example.com/sitemap.xml\n"
_SITEMAP = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    "  <url><loc>https://example.com/</loc></url>\n"
    "</urlset>\n"
)


def _mock_site() -> None:
    respx.get("https://example.com/robots.txt").mock(
        return_value=httpx.Response(
            200, text=_ROBOTS, headers={"content-type": "text/plain; charset=utf-8"}
        )
    )
    respx.get("https://example.com/sitemap.xml").mock(
        return_value=httpx.Response(200, text=_SITEMAP, headers={"content-type": "application/xml"})
    )
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(
            200,
            text="<html><head><title>Home</title></head><body>Hi</body></html>",
            headers={"content-type": "text/html"},
        )
    )


@respx.mock
def test_crawl_site_keeps_robots_and_sitemap_body():
    """非 HTML 的 content-type 不該讓 body 消失。"""
    _mock_site()

    connector = HTTPConnector("https://example.com")
    result = crawl_site(connector, seed_url="https://example.com", max_urls=5, max_depth=1)

    assert result.robots_txt is not None
    assert "sitemap:" in result.robots_txt.lower()
    assert result.sitemap_xml is not None
    assert result.sitemap_xml.lstrip().startswith("<?xml")


@respx.mock
def test_valid_robots_and_sitemap_produce_no_findings():
    """robots.txt 有宣告 sitemap、sitemap.xml 合法時，不該產出這兩項誤報。"""
    _mock_site()

    connector = HTTPConnector("https://example.com")
    result = crawl_site(connector, seed_url="https://example.com", max_urls=5, max_depth=1)
    findings = analyze_technical_seo(result, seed_url="https://example.com")

    ids = [f.id for f in findings]
    assert not [i for i in ids if "ROBOTS_NO_SITEMAP" in i]
    assert not [i for i in ids if "SITEMAP_INVALID_XML" in i]


@respx.mock
def test_html_pages_are_unaffected():
    """HTML 頁面照舊只走 `html` 欄位，不因這次修改而改變行為。"""
    _mock_site()

    connector = HTTPConnector("https://example.com")
    snapshot = connector.fetch_url("https://example.com/", fetched_at="")

    assert "<title>Home</title>" in snapshot.html
    assert "_raw_text" not in snapshot.headers
