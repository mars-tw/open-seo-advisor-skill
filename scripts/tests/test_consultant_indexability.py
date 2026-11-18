from unittest.mock import Mock
import json

import httpx
import pytest
import respx

from seo_advisor.analyzers.technical import analyze_technical_seo
from seo_advisor.connectors.http import HTTPConnector
from seo_advisor.crawler import CrawlResult, crawl_site, find_orphan_pages
from seo_advisor.models import PageSnapshot

SITE = "https://example.com"
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def snapshot(path, head="", *, status=200, final=None, **extra):
    return PageSnapshot(
        url=SITE + path,
        final_url=SITE + (final or path),
        status_code=status,
        fetched_at="",
        html=f"<html><head><title>Oak</title>{head}</head><body><h1>Oak</h1></body></html>",
        **extra,
    )


def audit(*pages, **options):
    result = CrawlResult(pages={page.url: page for page in pages})
    return result, analyze_technical_seo(result, seed_url=SITE + "/", **options)


def matching(findings, name):
    return [f for f in findings if f.id.startswith("SEO-" + name + "-")]


@pytest.mark.parametrize(
    "head",
    [
        '<meta name="googlebot" content="noindex">',
        '<meta name="robots" content="none">',
        '<meta name="robots" content="follow"><meta name="robots" content="noindex">',
    ],
)
def test_effective_google_directive_includes_evidence(head):
    _, findings = audit(snapshot("/", head))
    (finding,) = matching(findings, "NOINDEX_PRESENT")
    assert finding.evidence["rules"][SITE + "/"]
    _, preview = audit(snapshot("/", head), expect_indexing=False)
    assert not matching(preview, "NOINDEX_PRESENT")


def test_other_bot_and_multiple_independent_header_lines():
    _, findings = audit(snapshot("/", headers={"x-robots-tag": "otherbot: noindex"}))
    assert not matching(findings, "NOINDEX_PRESENT")
    with respx.mock:
        respx.get(SITE).mock(
            return_value=httpx.Response(
                200, headers=[("X-Robots-Tag", "otherbot: follow"), ("X-Robots-Tag", "noindex")]
            )
        )
        with HTTPConnector(SITE, rate_limiter=Mock()) as connector:
            page = connector.fetch_url(SITE)
    _, findings = audit(page)
    assert matching(findings, "NOINDEX_PRESENT")


def test_canonical_reports_source_and_distinguishes_unread_destination():
    tag = '<link rel="canonical" href="/retired">'
    result, findings = audit(snapshot("/product", tag), snapshot("/retired", status=410))
    (finding,) = matching(findings, "CANONICAL_TARGET_UNINDEXABLE")
    assert finding.affected_urls == [SITE + "/product"]
    assert finding.evidence["examples"][SITE + "/product"]["status"] == 410
    result, findings = audit(snapshot("/product", tag))
    assert result.unverified_canonicals == {SITE + "/product": SITE + "/retired"}
    assert not matching(findings, "CANONICAL_TARGET_UNINDEXABLE")
    _, findings = audit(
        snapshot("/product", tag), snapshot("/retired", '<meta name="robots" content="none">')
    )
    assert matching(findings, "CANONICAL_TARGET_UNINDEXABLE")


@respx.mock
def test_robots_declared_index_discovers_unlinked_product_without_leaving_site():
    robots = "Sitemap: /maps/index.xml\nSitemap: https://outside.example/map.xml"
    index = f'<sitemapindex xmlns="{NS}"><sitemap><loc>{SITE}/maps/items.xml</loc></sitemap></sitemapindex>'
    items = f'<urlset xmlns="{NS}"><url><loc>{SITE}/stock/</loc></url></urlset>'
    respx.get(SITE + "/robots.txt").respond(200, text=robots)
    root = respx.get(SITE + "/maps/index.xml").respond(200, text=index)
    child = respx.get(SITE + "/maps/items.xml").respond(200, text=items)
    respx.get(SITE).respond(200, html='<h1>Shop</h1><a href="/offers">Offers</a>')
    respx.get(SITE + "/offers").respond(200, html="<h1>Offers</h1>")
    respx.get(SITE + "/stock/").respond(200, html="<h1>Stock</h1>")
    with HTTPConnector(SITE, rate_limiter=Mock()) as connector:
        assert connector.probe().has_sitemap
        assert connector.list_urls(SITE, 10)[0].url == SITE + "/stock/"
        result = crawl_site(connector, seed_url=SITE, max_urls=10)
    assert SITE + "/stock/" in result.pages
    assert SITE + "/offers" in result.pages
    assert result.sitemap_sources == {
        SITE + "/maps/index.xml": "robots.txt",
        SITE + "/maps/items.xml": SITE + "/maps/index.xml",
    }
    assert root.call_count == child.call_count == 1
    assert not matching(analyze_technical_seo(result, seed_url=SITE), "SITEMAP_MISSING")


@pytest.mark.parametrize(
    "body",
    [
        "<html><body>Not found</body></html>",
        "<urlset/>",
        f'<urlset xmlns="{NS}"/>',
        f'<urlset xmlns="{NS}"><url><loc>/relative</loc></url></urlset>',
        f'<sitemapindex xmlns="{NS}"><sitemap/></sitemapindex>',
    ],
)
def test_sitemap_200_requires_sitemap_structure_and_valid_locations(body):
    url = SITE + "/maps/products.xml"
    result = CrawlResult(sitemap_documents={url: body})
    (finding,) = matching(analyze_technical_seo(result, seed_url=SITE), "SITEMAP_INVALID_STRUCTURE")
    assert finding.affected_urls == [url]
    assert finding.evidence["reason"]


def test_query_locale_identity_and_script_region_codes():
    en = "/item?lang=en"
    de = "/item?lang=de"
    tag = '<link rel="alternate" hreflang="zh-Hant-TW" href="' + SITE + de + '">'
    _, findings = audit(snapshot(en, tag), snapshot(de, tag))
    assert not matching(findings, "HREFLANG_INVALID_CODE")
    assert matching(findings, "HREFLANG_MISSING_SELF_REFERENCE")[0].affected_urls == [SITE + en]
    assert matching(findings, "HREFLANG_NON_RECIPROCAL")[0].affected_urls == [SITE + en]


def test_base_href_applies_to_crawl_links_and_canonical():
    from seo_advisor.crawler import _extract_links

    tag = '<base href="/catalog/"><base href="/ignored/"><link rel="canonical" href="old">'
    assert _extract_links(SITE + "/en/", tag + '<a href="oak/">Oak</a>') == [SITE + "/catalog/oak/"]
    _, findings = audit(snapshot("/en/", tag), snapshot("/catalog/old", status=404))
    assert matching(findings, "CANONICAL_TARGET_UNINDEXABLE")[0].affected_urls == [SITE + "/en/"]


def test_alias_content_compared_once_while_redirect_evidence_survives():
    _, findings = audit(
        snapshot("/old", final="/oak", redirect_chain=["/old", "/temporary"]), snapshot("/oak")
    )
    assert not matching(findings, "TITLE_DUPLICATE")
    assert matching(findings, "REDIRECT_CHAIN")


def test_robots_exclusions_separate_from_timeout_and_connection_errors():
    _, findings = audit(
        snapshot("/private", status=0, fetch_error_type="blocked_by_robots_txt"),
        snapshot("/slow", status=0, fetch_error_type="timeout"),
        snapshot("/offline", status=0, fetch_error_type="http_error"),
    )
    groups = {f.evidence["type"]: f.affected_urls for f in matching(findings, "FETCH_FAILED")}
    assert groups == {"timeout": [SITE + "/slow"], "http_error": [SITE + "/offline"]}


def test_only_a_self_link_does_not_make_a_page_discoverable():
    pages = [snapshot("/"), snapshot("/stock/")]
    result = CrawlResult(
        pages={p.url: p for p in pages}, link_graph={SITE + "/stock/": {SITE + "/stock/"}}
    )
    assert find_orphan_pages(result, SITE + "/") == [SITE + "/stock/"]


def test_module_scripts_do_not_trigger_blocking_hint():
    tags = "".join(f'<script type="module" src="/app{i}.js"></script>' for i in range(3))
    _, findings = audit(snapshot("/", tags))
    assert not matching(findings, "BLOCKING_SCRIPTS_HINT")


def test_local_cli_reports_linked_image_as_resource_and_keeps_sitemap_text(tmp_path):
    from typer.testing import CliRunner
    from seo_advisor.cli import app

    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        '<title>Photo</title><h1>Photo</h1><a href="photo.webp">View full image</a>',
        encoding="utf-8",
    )
    (site / "photo.webp").write_bytes(b"RIFF\x18\0\0\0WEBPVP8 " + bytes(16))
    (site / "robots.txt").write_text("User-agent: *\nSitemap: /sitemap.xml", encoding="utf-8")
    (site / "sitemap.xml").write_text(
        f'<urlset xmlns="{NS}"><url><loc>{SITE}/</loc></url></urlset>', encoding="utf-8"
    )
    output = tmp_path / "report"
    invocation = CliRunner().invoke(
        app, ["audit", "consultant", "--source", str(site), "--out", str(output)]
    )
    assert invocation.exit_code == 0, invocation.output
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    stats = report["scan_stats"]
    assert (stats["urls_crawled"], stats["html_pages"], stats["other_urls"]) == (2, 1, 1)
    assert stats["sitemaps_read"] == ["/sitemap.xml"]
    assert all("/photo.webp" not in f["affected_urls"] for f in report["findings"])
    assert not any(
        "ROBOTS_NO_SITEMAP" in f["id"] or "SITEMAP_INVALID" in f["id"] for f in report["findings"]
    )
