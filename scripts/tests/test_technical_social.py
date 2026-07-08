"""測試新增的技術 SEO 檢查：canonical 跨網域、Open Graph、JSON-LD。"""

from unittest.mock import patch

from seo_advisor.analyzers.technical import analyze_technical_seo
from seo_advisor.crawler import CrawlResult
from seo_advisor.models import PageSnapshot


def _page(url: str, html: str, status: int = 200) -> PageSnapshot:
    return PageSnapshot(
        url=url,
        status_code=status,
        final_url=url,
        headers={"content-type": "text/html"},
        html=html,
        fetched_at="t",
    )


def _result(url: str, html: str) -> CrawlResult:
    return CrawlResult(pages={url: _page(url, html)})


def test_canonical_cross_domain_flagged():
    html = '<html><head><link rel="canonical" href="https://other-site.com/x"></head><body>hi</body></html>'
    findings = analyze_technical_seo(_result("https://example.com/x", html), seed_url="https://example.com/x")
    assert any("CANONICAL_CROSS_DOMAIN" in f.id for f in findings)


def test_same_domain_canonical_not_flagged():
    html = '<html><head><link rel="canonical" href="https://example.com/x"></head><body>hi</body></html>'
    findings = analyze_technical_seo(_result("https://example.com/x", html), seed_url="https://example.com/x")
    assert not any("CANONICAL_CROSS_DOMAIN" in f.id for f in findings)


def test_www_vs_apex_canonical_not_flagged():
    """www.x.com ↔ x.com 是合法 canonicalization，不該被誤判成跨網域。"""
    html = '<html><head><link rel="canonical" href="https://example.com/x"></head><body>hi</body></html>'
    findings = analyze_technical_seo(
        _result("https://www.example.com/x", html), seed_url="https://www.example.com/x"
    )
    assert not any("CANONICAL_CROSS_DOMAIN" in f.id for f in findings)


def test_missing_open_graph_flagged():
    html = "<html><head><title>t</title></head><body>hi</body></html>"
    findings = analyze_technical_seo(_result("https://example.com/x", html), seed_url="https://example.com/x")
    assert any("MISSING_OPEN_GRAPH" in f.id for f in findings)


def test_complete_open_graph_not_flagged():
    html = (
        '<html><head><meta property="og:title" content="T">'
        '<meta property="og:image" content="https://example.com/c.jpg"></head><body>hi</body></html>'
    )
    findings = analyze_technical_seo(_result("https://example.com/x", html), seed_url="https://example.com/x")
    assert not any("MISSING_OPEN_GRAPH" in f.id for f in findings)


def test_noindex_page_missing_og_not_flagged():
    """noindex 頁本來就不打算被分享，缺 OG 不該報。"""
    html = '<html><head><meta name="robots" content="noindex"><title>t</title></head><body>hi</body></html>'
    findings = analyze_technical_seo(_result("https://example.com/x", html), seed_url="https://example.com/x")
    assert not any("MISSING_OPEN_GRAPH" in f.id for f in findings)


def test_api_path_missing_og_not_flagged():
    """API/後台路徑缺 OG 不該報（降噪）。"""
    html = "<html><head><title>t</title></head><body>hi</body></html>"
    findings = analyze_technical_seo(
        _result("https://example.com/api/data", html), seed_url="https://example.com/api/data"
    )
    assert not any("MISSING_OPEN_GRAPH" in f.id for f in findings)


def test_invalid_json_ld_flagged():
    html = '<html><head><script type="application/ld+json">{bad json,}</script></head><body>hi</body></html>'
    findings = analyze_technical_seo(_result("https://example.com/x", html), seed_url="https://example.com/x")
    assert any("INVALID_JSON_LD" in f.id for f in findings)


def test_valid_json_ld_not_flagged():
    html = (
        '<html><head><script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"Article"}</script></head><body>hi</body></html>'
    )
    findings = analyze_technical_seo(_result("https://example.com/x", html), seed_url="https://example.com/x")
    assert not any("INVALID_JSON_LD" in f.id for f in findings)


def test_html_parsed_once_per_page_not_five_times():
    """每頁 HTML 應該只被 BeautifulSoup(lxml) 解析一次，供 _check_page_metadata/
    _check_noindex/_check_canonical_target/_check_social_metadata/
    _check_structured_data 這 5 個檢查共用，而不是各自重新解析。"""
    html = (
        '<html><head><title>t</title>'
        '<meta name="description" content="d">'
        '<link rel="canonical" href="https://example.com/x">'
        '<meta property="og:title" content="T">'
        '<meta property="og:image" content="https://example.com/c.jpg">'
        '</head><body><h1>H</h1></body></html>'
    )
    with patch(
        "seo_advisor.analyzers.technical.BeautifulSoup", wraps=__import__("bs4").BeautifulSoup
    ) as mock_soup:
        analyze_technical_seo(_result("https://example.com/x", html), seed_url="https://example.com/x")
    assert mock_soup.call_count == 1
