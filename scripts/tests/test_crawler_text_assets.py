"""Reported #7/#9: preserve text assets without treating them as HTML pages."""

from unittest.mock import Mock

import pytest
import respx

from seo_advisor.analyzers.technical import analyze_technical_seo
from seo_advisor.connectors.http import HTTPConnector, _MAX_HTML_BYTES
from seo_advisor.crawler import crawl_site
from seo_advisor.models import PageSnapshot

ORIGIN = "https://example.com"
ROBOTS = f"User-agent: *\nAllow: /\nSitemap: {ORIGIN}/sitemap.xml\n"
SITEMAP = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    f"<url><loc>{ORIGIN}/</loc></url></urlset>"
)
HTML = "<html><head><title>Home</title></head><body>Home</body></html>"


@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize(
    "content_type",
    [
        "text/plain; charset=utf-8",
        "application/xml",
        "text/xml",
        "Application/XML; Charset=UTF-8",
        "application/atom+xml",
        "application/json",
        "application/ld+json",
    ],
)
@respx.mock
def test_text_body_survives_fresh_and_cached_fetch(content_type, cached):
    route = respx.get(f"{ORIGIN}/asset").respond(
        200, content=SITEMAP.encode(), headers={"content-type": content_type}
    )
    with HTTPConnector(ORIGIN, rate_limiter=Mock()) as connector:
        if cached:
            connector._safe_get(f"{ORIGIN}/asset", use_cache=True)
        snapshot = connector.fetch_url(f"{ORIGIN}/asset")
    assert snapshot.text == SITEMAP
    assert snapshot.html == ""
    assert "_raw_text" not in snapshot.headers
    assert route.call_count == 1


@pytest.mark.parametrize(
    "content_type", ["text/html", "TEXT/HTML; charset=UTF-8", "application/xhtml+xml"]
)
@respx.mock
def test_html_and_xhtml_still_have_parseable_html(content_type):
    respx.get(ORIGIN).respond(200, content=HTML.encode(), headers={"content-type": content_type})
    with HTTPConnector(ORIGIN, rate_limiter=Mock()) as connector:
        snapshot = connector.fetch_url(ORIGIN)
    assert snapshot.html == HTML
    assert snapshot.text == HTML


@pytest.mark.parametrize("cached", [False, True])
@respx.mock
def test_metadata_reaches_analyzer_without_false_findings(cached):
    robots = respx.get(f"{ORIGIN}/robots.txt").respond(
        200, text=ROBOTS, headers={"content-type": "text/plain"}
    )
    sitemap = respx.get(f"{ORIGIN}/sitemap.xml").respond(
        200, text=SITEMAP, headers={"content-type": "application/xml"}
    )
    respx.get(ORIGIN).respond(200, text=HTML, headers={"content-type": "text/html"})
    with HTTPConnector(ORIGIN, rate_limiter=Mock()) as connector:
        if cached:
            connector.probe()
        result = crawl_site(connector, seed_url=ORIGIN, max_urls=5)
    assert result.robots_txt == ROBOTS
    assert result.sitemap_xml == SITEMAP
    ids = [f.id for f in analyze_technical_seo(result, seed_url=ORIGIN)]
    assert not any("ROBOTS_NO_SITEMAP" in name or "SITEMAP_INVALID_XML" in name for name in ids)
    if cached:
        assert robots.call_count == sitemap.call_count == 1


@respx.mock
def test_probe_root_cache_matches_crawler_normalized_root():
    respx.get(f"{ORIGIN}/robots.txt").respond(404)
    respx.get(f"{ORIGIN}/sitemap.xml").respond(404)
    home = respx.get(ORIGIN).respond(200, text=HTML, headers={"content-type": "text/html"})
    with HTTPConnector(ORIGIN, rate_limiter=Mock()) as connector:
        connector.probe()
        result = crawl_site(connector, seed_url=ORIGIN, max_urls=1)
    assert set(result.pages) == {ORIGIN + "/"}
    assert home.call_count == 1


@respx.mock
def test_adding_valid_metadata_does_not_reduce_health_score():
    from seo_advisor.scoring import compute_site_health_score

    robots = respx.get(f"{ORIGIN}/robots.txt").respond(404)
    sitemap = respx.get(f"{ORIGIN}/sitemap.xml").respond(404)
    respx.get(ORIGIN).respond(200, text=HTML, headers={"content-type": "text/html"})
    with HTTPConnector(ORIGIN, rate_limiter=Mock()) as connector:
        absent = crawl_site(connector, seed_url=ORIGIN, max_urls=1)
    assert absent.robots_txt is absent.sitemap_xml is None
    robots.respond(200, text=ROBOTS, headers={"content-type": "text/plain"})
    sitemap.respond(200, text=SITEMAP, headers={"content-type": "application/xml"})
    with HTTPConnector(ORIGIN, rate_limiter=Mock()) as connector:
        present = crawl_site(connector, seed_url=ORIGIN, max_urls=1)
    before = compute_site_health_score(analyze_technical_seo(absent, seed_url=ORIGIN))
    after = compute_site_health_score(analyze_technical_seo(present, seed_url=ORIGIN))
    assert after > before


@pytest.mark.parametrize("sitemap_body", ["", "<urlset>"])
@respx.mock
def test_empty_or_malformed_sitemap_is_still_invalid(sitemap_body):
    respx.get(f"{ORIGIN}/robots.txt").respond(
        200, text="User-agent: *", headers={"content-type": "text/plain"}
    )
    respx.get(f"{ORIGIN}/sitemap.xml").respond(
        200, text=sitemap_body, headers={"content-type": "application/xml"}
    )
    respx.get(ORIGIN).respond(200, text=HTML, headers={"content-type": "text/html"})
    with HTTPConnector(ORIGIN, rate_limiter=Mock()) as connector:
        result = crawl_site(connector, seed_url=ORIGIN, max_urls=1)
    assert result.sitemap_xml == sitemap_body
    ids = [f.id for f in analyze_technical_seo(result, seed_url=ORIGIN)]
    assert any("SITEMAP_INVALID_XML" in name for name in ids)
    assert any("ROBOTS_NO_SITEMAP" in name for name in ids)


@pytest.mark.parametrize(
    "media", ["image/png", "application/pdf", "application/octet-stream", "application/notxml", ""]
)
@respx.mock
def test_binary_and_unspecified_types_are_not_decoded(media):
    respx.get(f"{ORIGIN}/asset").respond(
        200, content=b"\x00\xffpayload", headers={"content-type": media}
    )
    with HTTPConnector(ORIGIN, rate_limiter=Mock()) as connector:
        snapshot = connector.fetch_url(f"{ORIGIN}/asset")
    assert snapshot.text is None
    assert snapshot.html == ""


@respx.mock
def test_declared_charset_is_honored_for_text():
    content = "User-agent: *\n# 繁體中文測試\n"
    respx.get(f"{ORIGIN}/robots.txt").respond(
        200, content=content.encode("big5"), headers={"content-type": "text/plain; charset=big5"}
    )
    with HTTPConnector(ORIGIN, rate_limiter=Mock()) as connector:
        assert connector.fetch_url(f"{ORIGIN}/robots.txt").text == content


@pytest.mark.parametrize("cached", [False, True])
@respx.mock
def test_text_size_limit_is_preserved(cached):
    respx.get(f"{ORIGIN}/oversized").respond(
        200,
        content=b"not-downloaded",
        headers={"content-type": "text/plain", "content-length": str(_MAX_HTML_BYTES + 1)},
    )
    with HTTPConnector(ORIGIN, rate_limiter=Mock()) as connector:
        if cached:
            connector._safe_get(f"{ORIGIN}/oversized", use_cache=True)
        snapshot = connector.fetch_url(f"{ORIGIN}/oversized")
    assert snapshot.text == ""
    assert not snapshot.html


@respx.mock
def test_wire_header_cannot_replace_robots_body():
    respx.get(f"{ORIGIN}/robots.txt").respond(
        200, text="", headers={"content-type": "text/plain", "_raw_text": ROBOTS.replace("\n", " ")}
    )
    respx.get(f"{ORIGIN}/sitemap.xml").respond(404)
    respx.get(ORIGIN).respond(200, text=HTML, headers={"content-type": "text/html"})
    with HTTPConnector(ORIGIN, rate_limiter=Mock()) as connector:
        result = crawl_site(connector, seed_url=ORIGIN, max_urls=1)
    assert result.robots_txt == ""


def test_legacy_snapshot_can_omit_text():
    snapshot = PageSnapshot(url="/", status_code=200, final_url="/", html=HTML, fetched_at="")
    assert snapshot.text is None


def test_text_response_unknown_charset_falls_back_to_utf8():
    from seo_advisor.connectors.text_response import snapshot_body_fields

    fields = snapshot_body_fields("文字".encode(), "text/plain", "not-an-encoding")
    assert fields == {"html": "", "text": "文字"}


@pytest.mark.parametrize("media,body", [("text/plain", ROBOTS), ("application/xml", SITEMAP)])
@respx.mock
def test_wordpress_public_text_uses_same_body_contract(media, body):
    from seo_advisor.connectors.wordpress import WordPressAPIConnector

    respx.get(f"{ORIGIN}/asset").respond(200, text=body, headers={"content-type": media})
    with WordPressAPIConnector(ORIGIN) as connector:
        snapshot = connector.fetch_url(f"{ORIGIN}/asset")
    assert snapshot.text == body
    assert snapshot.html == ""


@respx.mock
def test_non_html_content_is_not_crawled_as_html():
    respx.get(f"{ORIGIN}/robots.txt").respond(404)
    respx.get(f"{ORIGIN}/sitemap.xml").respond(404)
    respx.get(ORIGIN).respond(
        200, text='<a href="/should-not-crawl">text</a>', headers={"content-type": "text/plain"}
    )
    forbidden = respx.get(f"{ORIGIN}/should-not-crawl").respond(200, text=HTML)
    with HTTPConnector(ORIGIN, rate_limiter=Mock()) as connector:
        result = crawl_site(connector, seed_url=ORIGIN, max_urls=5)
    assert len(result.pages) == 1
    assert forbidden.call_count == 0


@respx.mock
def test_sitemap_index_budget_counts_unique_documents_across_children():
    respx.get(f"{ORIGIN}/sitemap.xml").respond(
        200,
        text=f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>{ORIGIN}/first.xml</loc></sitemap><sitemap><loc>{ORIGIN}/second.xml</loc></sitemap></sitemapindex>',
        headers={"content-type": "application/xml"},
    )
    for name, pages in [
        ("first", ["/#one", "/#two"]),
        ("second", ["/#three", "/about#team", "/extra"]),
    ]:
        body = (
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{ORIGIN}{page}</loc></url>" for page in pages)
            + "</urlset>"
        )
        respx.get(f"{ORIGIN}/{name}.xml").respond(
            200, text=body, headers={"content-type": "application/xml"}
        )
    with HTTPConnector(ORIGIN, rate_limiter=Mock()) as connector:
        records = connector.list_urls(ORIGIN, limit=2)
    assert [r.url for r in records] == [ORIGIN + "/", ORIGIN + "/about"]
