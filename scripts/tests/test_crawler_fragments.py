"""A fragment targets part of a document, never another crawl-budget entry."""

from collections import Counter
from urllib.parse import urldefrag
from unittest.mock import Mock

import pytest
import respx

from seo_advisor.analyzers.technical import analyze_technical_seo
from seo_advisor.connectors.http import HTTPConnector
from seo_advisor.crawler import crawl_site, find_orphan_pages
from seo_advisor.models import PageSnapshot, UrlRecord


class SnapshotConnector:
    """Expose exact fetch arguments while serving fragments as the same document."""

    def __init__(self, pages, records=(), final_urls=None):
        self.pages = pages
        self.records = records
        self.final_urls = final_urls or {}
        self.fetched = []
        self.list_seeds = []

    def list_urls(self, seed, limit):
        self.list_seeds.append(seed)
        return self.records

    def fetch_url(self, url, *, fetched_at=""):
        self.fetched.append(url)
        document = urldefrag(url).url
        return PageSnapshot(
            url=url,
            final_url=self.final_urls.get(document, document),
            status_code=200 if document in self.pages else 404,
            html=self.pages.get(document, ""),
            fetched_at=fetched_at,
        )


def page(title, links=""):
    return f"<html><head><title>{title}</title></head><body><h1>{title}</h1>{links}</body></html>"


@pytest.mark.parametrize(
    "seed", ["https://example.com/", "https://example.com/#intro", "https://example.com#intro"]
)
@respx.mock
def test_fragment_links_do_not_create_duplicate_titles_or_consume_page_budget(monkeypatch, seed):
    monkeypatch.setattr("seo_advisor.connectors.http.ensure_host_allowed", lambda *a, **k: None)
    respx.get("https://example.com/robots.txt").respond(404)
    respx.get("https://example.com/sitemap.xml").respond(404)
    home = respx.get("https://example.com/").respond(
        200,
        text=page(
            "Home",
            '<a href="#intro">Intro</a><a href="/#contact">Contact</a><a href="https://example.com/#team">Team</a><a href="/next#details">Next</a>',
        ),
        headers={"content-type": "text/html"},
    )
    next_page = respx.get("https://example.com/next").respond(
        200, text=page("Next page"), headers={"content-type": "text/html"}
    )
    with HTTPConnector(seed, rate_limiter=Mock()) as connector:
        result = crawl_site(connector, seed_url=seed, max_urls=2)
    assert set(result.pages) == {"https://example.com/", "https://example.com/next"}
    assert home.call_count == next_page.call_count == 1
    assert all("#" not in url for targets in result.link_graph.values() for url in targets)
    findings = analyze_technical_seo(result, seed_url=seed)
    assert not any("TITLE_DUPLICATE" in finding.id for finding in findings)


def test_cross_page_relative_anchors_resolve_against_final_url_and_keep_query_data():
    connector = SnapshotConnector(
        {
            "https://example.com/guide/start": page(
                "Start",
                '<a href="../products?tag=tea%23gold&sort=price#top">Tea</a><a href="../products?tag=tea%23gold&sort=price#reviews">Reviews</a><a href="../products?tag=tea%23gold&sort=name#top">Other sort</a><a href="../products/archive#top">Archive</a>',
            ),
            "https://example.com/products?tag=tea%23gold&sort=price": page("Tea by price"),
            "https://example.com/products?tag=tea%23gold&sort=name": page("Tea by name"),
            "https://example.com/products/archive": page("Archive"),
        }
    )
    result = crawl_site(connector, seed_url="https://example.com/guide/start#intro", max_urls=4)
    expected = set(connector.pages)
    assert set(result.pages) == expected
    assert result.link_graph["https://example.com/guide/start"] == expected - {
        "https://example.com/guide/start"
    }
    assert Counter(url for url in connector.fetched if url in expected) == Counter(
        {url: 1 for url in expected}
    )
    assert connector.list_seeds == ["https://example.com/guide/start"]


def test_sitemap_fragment_records_are_normalized_before_queueing_and_preserve_depth():
    connector = SnapshotConnector(
        {
            "https://example.com/": page("Home"),
            "https://example.com/about": page("About"),
            "https://example.com/products?q=red%23gold": page("Products"),
        },
        [
            UrlRecord(url="https://example.com/#contact", source="sitemap", discovered_depth=0),
            UrlRecord(url="https://example.com/#team", source="sitemap", discovered_depth=0),
            UrlRecord(url="/about#staff", source="sitemap", discovered_depth=1),
            UrlRecord(url="/about#history", source="sitemap", discovered_depth=1),
            UrlRecord(
                url="/products?q=red%23gold#description", source="sitemap", discovered_depth=1
            ),
            UrlRecord(url="/too-deep#section", source="sitemap", discovered_depth=3),
        ],
    )
    result = crawl_site(connector, seed_url="https://example.com/#start", max_urls=3, max_depth=1)
    assert set(result.pages) == set(connector.pages)
    assert "https://example.com/" not in find_orphan_pages(result, "https://example.com/#start")
    assert all("#" not in url for url in connector.fetched)
    assert not any("too-deep" in url for url in connector.fetched)


def test_local_archive_style_paths_keep_distinct_files_and_querystrings():
    connector = SnapshotConnector(
        {
            "/docs/index.html": page(
                "Index",
                '<a href="./index.html#first">Same</a><a href="../about.html#team">About</a><a href="../about.html?lang=en#team">English</a>',
            ),
            "/about.html": page("About"),
            "/about.html?lang=en": page("About in English"),
        }
    )
    result = crawl_site(connector, seed_url="/docs/index.html#top", max_urls=3)
    assert set(result.pages) == set(connector.pages)
    assert Counter(url for url in connector.fetched if url in connector.pages) == Counter(
        {url: 1 for url in connector.pages}
    )


@respx.mock
def test_http_sitemap_fragment_records_fetch_each_document_once(monkeypatch):
    monkeypatch.setattr("seo_advisor.connectors.http.ensure_host_allowed", lambda *a, **k: None)
    respx.get("https://example.com/robots.txt").respond(404)
    respx.get("https://example.com/sitemap.xml").respond(
        200,
        text="""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://example.com/#intro</loc></url>
        <url><loc>https://example.com/#contact</loc></url>
        <url><loc>https://example.com/about#team</loc></url>
        <url><loc>https://example.com/about#history</loc></url>
        </urlset>""",
        headers={"content-type": "application/xml"},
    )
    home = respx.get("https://example.com/").respond(
        200, text=page("Home"), headers={"content-type": "text/html"}
    )
    about = respx.get("https://example.com/about").respond(
        200, text=page("About"), headers={"content-type": "text/html"}
    )
    with HTTPConnector("https://example.com", rate_limiter=Mock()) as connector:
        result = crawl_site(connector, seed_url="https://example.com/#entry", max_urls=2)
    assert set(result.pages) == {"https://example.com/", "https://example.com/about"}
    assert home.call_count == about.call_count == 1


def test_relative_fragment_links_use_redirect_destination_as_base():
    connector = SnapshotConnector(
        {
            "https://example.com/old": page("Guide", '<a href="../help?q=a%23b#answer">Help</a>'),
            "https://example.com/new/help?q=a%23b": page("Help"),
        },
        final_urls={"https://example.com/old": "https://example.com/new/guide/start#top"},
    )
    result = crawl_site(connector, seed_url="https://example.com/old#entry", max_urls=2)
    assert set(result.pages) == set(connector.pages)
    assert result.link_graph["https://example.com/old"] == {"https://example.com/new/help?q=a%23b"}


def test_duplicate_seed_records_keep_shallower_depth_for_discovery():
    connector = SnapshotConnector(
        {
            "https://example.com/": page("Home", '<a href="/child#details">Child</a>'),
            "https://example.com/child": page("Child"),
        },
        [
            UrlRecord(url="https://example.com/#deep", source="sitemap", discovered_depth=2),
            UrlRecord(url="https://example.com/#start", source="seed", discovered_depth=0),
        ],
    )
    result = crawl_site(connector, seed_url="https://example.com/", max_urls=2, max_depth=1)
    assert set(result.pages) == set(connector.pages)
    assert connector.fetched.count("https://example.com/") == 1
