import json
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from typer.testing import CliRunner

from seo_advisor.cli import app
from seo_advisor.url_utils import sitemap_url


def invoke(*args, expected=0):
    result = CliRunner().invoke(app, [str(arg) for arg in args])
    assert result.exit_code == expected, result.output
    return result.output


def audit(site, out, *options):
    invoke("audit", "consultant", "--source", site, "--out", out, *options)
    return json.loads((out / "report.json").read_bytes())


def write_page(path, extra=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"<!doctype html><html><head><title>{path.stem}</title>{extra}</head>"
        "<body><h1>Service</h1></body></html>",
        encoding="utf-8",
    )


def test_sitemap_url_preserves_existing_escapes_query_and_reserved_delimiters():
    source = "https://shop.example/已 編/%2F/50%?series=a%2Fb&model=A+B"
    assert (
        sitemap_url(source)
        == "https://shop.example/%E5%B7%B2%20%E7%B7%A8/%2F/50%25?series=a%2Fb&model=A+B"
    )


def apply_review(args, out):
    invoke(*args)
    plan = json.loads((out / "fix-plan.json").read_bytes())
    invoke(*args, "--apply", "--confirm", "APPLY " + plan["plan_id"])
    return plan


def test_local_sitemap_uses_equivalent_canonical_encodes_paths_and_excludes_tool_output(tmp_path):
    site, out = tmp_path / "source", tmp_path / "plan"
    origin = "https://shop.example"
    write_page(site / "index.html", '<link rel="canonical" href="https://SHOP.EXAMPLE:443/">')
    write_page(
        site / "de/pump.html", '<link rel="canonical" href="https://shop.example:443/de/pump.html">'
    )
    write_page(site / "diff.html", '<link rel="canonical" href="/diff.html?lang=de">')
    write_page(site / "zh/報價 表.html", '<link rel="canonical" href="/zh/報價 表.html">')
    write_page(site / "old report/index.html")
    write_page(site / "report/about.html")
    write_page(site / "business/report.html")
    audit(site, site / "old report")
    # Simulate a report produced before the generator meta marker was introduced.
    legacy = site / "old report/report.html"
    legacy.write_text(
        legacy.read_text(encoding="utf-8").replace(
            '<meta name="generator" content="Open SEO Advisor Consultant">', ""
        ),
        encoding="utf-8",
    )
    first = audit(site, site / "report")
    second = audit(site, site / "report")
    assert first["scan_stats"]["html_pages"] == second["scan_stats"]["html_pages"] == 7
    missing = next(f["id"] for f in second["findings"] if "SITEMAP_MISSING" in f["id"])
    plan = apply_review(
        [
            "fix",
            "engineer",
            "--source",
            site,
            "--finding-id",
            missing,
            "--from-report",
            site / "report/report.json",
            "--site-url",
            origin,
            "--out",
            out,
        ],
        out,
    )
    locs = {node.text for node in ElementTree.parse(site / "sitemap.xml").findall(".//{*}loc")}
    assert locs == {
        origin + path
        for path in (
            "/",
            "/de/pump.html",
            "/zh/%E5%A0%B1%E5%83%B9%20%E8%A1%A8.html",
            "/old%20report/index.html",
            "/business/report.html",
            "/report/about.html",
        )
    }
    assert any("/diff.html?lang=de" in warning for warning in plan["warnings"])


def test_real_hreflang_preview_apply_encoding_and_language_identity(tmp_path):
    site, out = tmp_path / "source", tmp_path / "review"
    site.mkdir()
    target = site / "tw.html"
    source = '<html><head><meta charset = "big5"><title>台灣供應商</title></head><body>齒輪報價</body></html>'.encode(
        "big5"
    )
    target.write_bytes(source)
    mapping = tmp_path / "languages.json"
    cluster = {
        "id": "gear",
        "alternates": {
            "en-US": "https://shop.example/us",
            "en-us": "https://shop.example/other",
            "zh-hant-tw": "https://shop.example/tw",
        },
        "targets": {"ZH-HANT-TW": "tw.html"},
    }
    mapping.write_text(json.dumps({"clusters": [cluster]}), encoding="utf-8")
    args = ["fix", "hreflang-html", "--source", site, "--map", mapping, "--out", out]
    assert "同一語系" in invoke(*args, expected=1)
    assert target.read_bytes() == source and not (out / "fix-plan.json").exists()
    cluster["alternates"]["en-us"] = "https://SHOP.EXAMPLE:443/us"
    mapping.write_text(json.dumps({"clusters": [cluster]}), encoding="utf-8")
    apply_review(args, out)
    soup = BeautifulSoup(target.read_bytes(), "lxml")
    assert soup.title.string == "台灣供應商" and soup.body.string == "齒輪報價"
    assert soup.meta["charset"] == "utf-8"
    assert [tag["hreflang"] for tag in soup.select("link[hreflang]")] == ["en-US", "zh-Hant-TW"]
    manifest = next(site.rglob("applied-manifest.json")).parent
    invoke(
        "fix",
        "rollback",
        "--source",
        site,
        "--backup",
        manifest,
        "--apply",
        "--confirm",
        "ROLLBACK " + manifest.name,
    )
    assert target.read_bytes() == source


def test_local_audit_uses_confirmed_sitemap_origin_routes_and_bom(tmp_path):
    site = tmp_path / "source"
    write_page(site / "index.html", '<link rel="canonical" href="/">')
    home = site / "index.html"
    home.write_text(
        home.read_text().replace(
            "</body>",
            '<a href="/catalog/">catalog</a>'
            '<a href="/downloads/misc">file</a><a href="/catalog/index.html?ref=nav">shop</a>'
            '<a href="/offers">Offers</a></body>',
        )
    )
    (site / "downloads").mkdir()
    (site / "downloads/misc").write_bytes(b"\xff\x00\xfe\x03")
    write_page(site / "catalog/index.html")
    (site / "offers").write_text(
        "<!doctype html><html><head><title>Offers</title>"
        '<meta name="robots" content="noindex"></head><body></body></html>',
        encoding="utf-8-sig",
    )
    (site / "maps").mkdir()
    (site / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: https://SHOP.EXAMPLE:443/maps/products.xml\n"
    )
    (site / "maps/products.xml").write_text(
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        "<url><loc>https://shop.example/offers</loc></url></urlset>"
    )
    report = audit(site, tmp_path / "audit", "--site-url", "https://shop.example")
    findings = report["findings"]
    assert not any("SITEMAP_MISSING" in f["id"] for f in findings)
    assert any(
        "NOINDEX" in f["id"] and any(u.endswith("/offers") for u in f["affected_urls"])
        for f in findings
    )
    assert report["scan_stats"]["status_code_distribution"].get("4xx", 0) == 0
    assert report["scan_stats"]["urls_skipped"] == 0
    assert not any(
        "HTTP_ERRORS" in finding["id"] and any("/catalog/" in url for url in finding["affected_urls"])
        for finding in findings
    )
    assert any("/maps/products.xml" in u for u in report["scan_stats"]["sitemaps_read"])
    assert "/downloads/misc" in report["scan_stats"]["unclassified_content_urls"]
    unknown = audit(site, tmp_path / "unknown")
    assert "https://SHOP.EXAMPLE:443/maps/products.xml" in unknown["scan_stats"]["sitemap_pending"]
    assert not any("SITEMAP_MISSING" in f["id"] for f in unknown["findings"])
