"""Read back real consultant CLI reports from deterministic HTTP fixtures."""

import gzip
import json
from urllib.parse import urlsplit

import httpx
import pytest
import respx
from typer.testing import CliRunner

from seo_advisor.cli import app
from seo_advisor.sitemaps import NS

SITE = "https://93.184.215.14"
SITEMAP = "/sitemap.xml"


def urlset(paths):
    return (
        f'<urlset xmlns="{NS[1:-1]}">'
        + "".join(f"<url><loc>{SITE}{path}</loc></url>" for path in paths)
        + "</urlset>"
    )


def index(paths):
    return (
        f'<sitemapindex xmlns="{NS[1:-1]}">'
        + "".join(f"<sitemap><loc>{SITE}{path}</loc></sitemap>" for path in paths)
        + "</sitemapindex>"
    )


def page(title, head="", body=""):
    return httpx.Response(
        200,
        html=f"""<html><head><title>{title}</title><meta name="description" content="{title}">
        <meta property="og:title" content="{title}"><meta property="og:image" content="/hero.webp">
        {head}</head><body><h1>{title}</h1>{body}</body></html>""",
    )


def xml(body):
    return httpx.Response(200, text=body, headers={"content-type": "application/xml"})


def alt(lang, path):
    return f'<link rel="alternate" hreflang="{lang}" href="{SITE}{path}">'


@pytest.fixture
def audit(tmp_path, monkeypatch):
    monkeypatch.setattr("seo_advisor.security.rate_limiter.RateLimiter.wait", lambda self: None)

    def run(files, *options, robots="Sitemap: " + SITE + SITEMAP):
        calls = []
        routes = {"/": page("Home"), "/robots.txt": httpx.Response(200, text=robots), **files}

        def respond(request):
            path = request.url.raw_path.decode()
            calls.append(path)
            response = routes.get(path, httpx.Response(404))
            if isinstance(response, Exception):
                raise response
            return response

        with respx.mock(assert_all_called=False) as mocked:
            mocked.route(host=urlsplit(SITE).hostname).mock(side_effect=respond)
            result = CliRunner().invoke(
                app, ["audit", "consultant", "--url", SITE, "--out", str(tmp_path), *options]
            )
        assert result.exit_code == 0, (result.output, result.exception)
        report = json.loads((tmp_path / "report.json").read_text("utf-8"))
        return report, calls

    return run


def findings(report):
    return {item["id"].rsplit("-", 1)[0].removeprefix("SEO-"): item for item in report["findings"]}


@pytest.mark.parametrize("fmt", ["rss", "atom", "text", "gzip_xml", "gzip_text"])
def test_alternate_formats_discover_real_product(audit, fmt):
    product = SITE + "/products/oak"
    content = {
        "rss": f'<rss version="2.0"><channel><title>Shop</title><link>{SITE}/</link><description>Catalogue</description><item><title>Oak</title><link>{product}</link></item></channel></rss>',
        "atom": f'<a:feed xmlns:a="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/"><a:id>{SITE}/feed</a:id><a:title>Shop</a:title><a:author><a:name>Shop</a:name></a:author><a:updated>2026-11-17T10:00:00Z</a:updated><a:entry><a:id>{product}</a:id><a:title>Oak</a:title><a:updated>2026-11-17T10:00:00Z</a:updated><a:link rel="self" href="{SITE}/feed/1"/><media:content url="{SITE}/oak.jpg"/><a:link type="text/html" href="{product}"/></a:entry></a:feed>',
        "text": product + "\n",
        "gzip_xml": urlset(["/products/oak"]),
        "gzip_text": product + "\n",
    }[fmt].encode()
    headers = {
        "content-type": {
            "rss": "application/rss+xml",
            "atom": "application/atom+xml",
            "text": "text/plain",
        }.get(fmt, "application/gzip")
    }
    response = httpx.Response(
        200, content=gzip.compress(content) if fmt.startswith("gzip") else content, headers=headers
    )
    report, calls = audit({SITEMAP: response, "/products/oak": page("Oak")})
    assert "/products/oak" in calls
    assert "/feed/1" not in calls and "/oak.jpg" not in calls
    assert not any(key.startswith("SITEMAP_") for key in findings(report))


def test_bad_child_core_status_and_sibling(audit):
    report, calls = audit(
        {
            SITEMAP: xml(index(["/part1.xml", "/part2.xml"])),
            "/part1.xml": xml(urlset(["/stock"])),
            "/stock": page("Stock"),
        }
    )
    errors = findings(report)["SITEMAP_UNREADABLE"]
    assert "/stock" in calls
    assert errors["affected_urls"] == [SITE + "/part2.xml"]
    assert errors["evidence"]["statuses"] == {SITE + "/part2.xml": 404}
    assert report["site_health_score"] < 100


def test_fifty_complete_children_and_reported_cutoff(audit):
    files = {}
    paths = []
    for i in range(1, 52):
        path = f"/map{i}.xml"
        paths.append(path)
        files[path] = xml(urlset([f"/product{i}"]))
        files[f"/product{i}"] = page(f"Product {i}")
    files[SITEMAP] = xml(index(paths))
    report, calls = audit(files)
    assert "/product50" in calls and "/map51.xml" not in calls
    assert report["scan_stats"]["sitemap_pending"] == {
        SITE + "/map51.xml": "超過子索引深度或 sitemap 檔案數上限"
    }
    assert len(report["scan_stats"]["sitemaps_read"]) == 51
    report, calls = audit(files, "--max-sitemap-files", "51")
    assert "/product51" in calls
    assert not report["scan_stats"]["sitemap_pending"]


def test_probe_and_discovery_share_the_root_budget(audit):
    roots = [f"/root{i}.xml" for i in range(5)]
    robots = "\n".join("Sitemap: " + SITE + path for path in roots)
    report, calls = audit({}, "--max-sitemap-files", "2", robots=robots)
    assert [url for url in calls if url in roots] == roots[:2]
    assert set(report["scan_stats"]["sitemap_statuses"].values()) == {404}
    assert all(SITE + path in report["scan_stats"]["sitemap_pending"] for path in roots[2:])


def test_reciprocity_uses_observed_redirect_targets(audit):
    fr, old, en = "/fr/", "/en-2025/", "/en/"
    files = {
        SITEMAP: xml(urlset(["/", fr, old])),
        fr: page("FR", alt("fr", fr) + alt("en", old)),
        old: httpx.Response(301, headers={"location": en}),
        en: page("EN", alt("en", en)),
    }
    report, _ = audit(files)
    problems = findings(report)
    assert problems["HREFLANG_NON_RECIPROCAL"]["affected_urls"] == [SITE + fr]
    assert problems["HREFLANG_REDIRECT"]["evidence"]["targets"][SITE + fr][0]["final"] == SITE + en
    files[en] = page("EN", alt("en", en) + alt("fr", fr))
    report, _ = audit(files)
    assert "HREFLANG_NON_RECIPROCAL" not in findings(report)


def test_googlebot_rule_and_preview_intent(audit):
    files = {
        SITEMAP: xml(urlset(["/", "/closed"])),
        "/": page("Home", '<meta name="robots" content="index,follow">'),
        "/closed": page("Closed", '<meta name="robots" content="noindex">'),
    }
    robots = (
        "User-agent: Googlebot\nDisallow: /\nUser-agent: *\nAllow: /\nSitemap: " + SITE + SITEMAP
    )
    live, _ = audit(files, robots=robots)
    assert findings(live)["GOOGLEBOT_BLOCKED"]["affected_urls"] == [SITE + "/"]
    preview, _ = audit(files, "--preview", robots=robots)
    assert findings(preview)["PREVIEW_INDEXABLE"]["affected_urls"] == [SITE + "/"]
    assert findings(preview)["PREVIEW_INDEXABLE"]["evidence"]["observed_directives"] == {
        SITE + "/": ["meta robots: index,follow"]
    }
    assert "NOINDEX_PRESENT" not in findings(preview)


def test_confirmed_metadata_and_title_groups_pass_all_urls_to_handoff(audit):
    paths = [f"/item/{i}" for i in range(52)]
    pages = {
        path: httpx.Response(200, html="<title>Shared title</title><p>Catalog</p>")
        for path in paths
    }
    report, _ = audit({SITEMAP: xml(urlset(paths)), **pages})
    found = findings(report)
    for category in ("H1_MISSING", "TITLE_DUPLICATE"):
        assert set(found[category]["affected_urls"]) == {SITE + path for path in paths}
    assert len(found["TITLE_DUPLICATE"]["evidence"]["examples"]["Shared title"]) == 5


def test_original_consultant_regressions_in_one_report(audit):
    en, de = "/item?lang=en", "/item?lang=de"
    links = "".join(
        f'<a href="{p}">Page</a>' for p in [en, de, "/tw/", "/old", "/now", "/image.webp"]
    )
    legacy = "".join(
        f'<script type="application/x-javascript" src="/app{i}.js"></script>' for i in range(3)
    )
    modules = legacy.replace("application/x-javascript", "module")
    paths = [
        "/",
        en,
        de,
        "/tw/",
        "/old",
        "/now",
        "/catalog/retired",
        "/private",
        "/slow",
        "/alone",
        "/image.webp",
        "/preview",
    ]
    files = {
        "/": page("Home", modules, links),
        SITEMAP: xml(index(["/maps/products.xml"])),
        "/maps/products.xml": xml(urlset(paths)),
        "/old": httpx.Response(301, headers={"location": "/now"}),
        "/now": page("Single final document"),
        en: page("EN", alt("zh-Hant-TW", de)),
        de: page("DE", alt("zh-Hant-TW", de)),
        "/tw/": page(
            "TW",
            '<base href="/catalog/"><link rel="canonical" href="retired">',
            '<a href="oak">Oak</a>',
        ),
        "/catalog/retired": httpx.Response(410),
        "/catalog/oak": page("Oak", legacy),
        "/slow": httpx.ReadTimeout("timed out"),
        "/alone": page("Alone", body='<a href="/alone">Here</a>'),
        "/image.webp": httpx.Response(200, content=b"RIFF", headers={"content-type": "image/webp"}),
        "/preview": page("Preview", '<meta name="googlebot" content="none">'),
    }
    report, calls = audit(
        files, robots="User-agent: *\nDisallow: /private\nSitemap: " + SITE + SITEMAP
    )
    found, stats = findings(report), report["scan_stats"]
    assert found["NOINDEX_PRESENT"]["affected_urls"] == [SITE + "/preview"]
    assert found["CANONICAL_TARGET_UNINDEXABLE"]["affected_urls"] == [SITE + "/tw/"]
    assert set(stats["sitemaps_read"]) == {SITE + SITEMAP, SITE + "/maps/products.xml"}
    assert not {"HREFLANG_INVALID_CODE", "TITLE_DUPLICATE"}.intersection(found)
    assert found["HREFLANG_MISSING_SELF_REFERENCE"]["affected_urls"] == [SITE + en]
    assert found["HREFLANG_NON_RECIPROCAL"]["affected_urls"] == [SITE + en]
    assert "/catalog/oak" in calls and "/tw/oak" not in calls
    assert stats["robots_excluded_urls"] == [SITE + "/private"]
    assert found["FETCH_FAILED"]["affected_urls"] == [SITE + "/slow"]
    assert found["FETCH_FAILED"]["evidence"]["type"] == "timeout"
    assert found["ORPHAN_PAGES"]["affected_urls"] == [SITE + "/alone"]
    assert found["BLOCKING_SCRIPTS_HINT"]["affected_urls"] == [SITE + "/catalog/oak"]
    assert stats["html_pages"] == 9 and stats["other_urls"] == 4
    assert not any(SITE + "/image.webp" in f["affected_urls"] for f in found.values())
    bad, _ = audit({SITEMAP: xml("<html><body>Not found</body></html>")})
    assert findings(bad)["SITEMAP_INVALID_STRUCTURE"]["affected_urls"] == [SITE + SITEMAP]
