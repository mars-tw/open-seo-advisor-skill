"""Operator workflows from the 0.6.1 audit. Exercise CLI and inspect the written files."""

import json

import pytest
from typer.testing import CliRunner

from seo_advisor.cli import app
from seo_advisor.growth.models import AnalyticsMetricRow
from seo_advisor.growth.providers.mock import MockAnalyticsProvider
from seo_advisor.writers.providers.mock import MockProvider


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_php_source_produces_an_unscored_report_in_every_format(tmp_path):
    site = tmp_path / "public"
    site.mkdir()
    (site / "index.php").write_text("<h1>Parts</h1>", encoding="utf-8")
    (site / "robots.txt").write_text("User-agent: *\nAllow: /\nSitemap: https://shop.example/sitemap.xml\n")
    (site / "sitemap.xml").write_text(
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<url><loc>https://shop.example/</loc></url></urlset>'
    )
    out = tmp_path / "reports"
    cli = CliRunner().invoke(app, ["audit", "consultant", "--source", str(site), "--out", str(out)])
    assert cli.exit_code == 2, cli.output
    assert "無法評分" in cli.output
    result = read_json(out / "report.json")
    assert result["scan_stats"]["analyzed_html_pages"] == 0
    assert result["site_health_score"] is None
    for name in ("report.md", "report-beginner.md", "report.html"):
        text = (out / name).read_text(encoding="utf-8")
        assert "無法評分" in text and "100/100" not in text


@pytest.mark.parametrize("scenario,expected_issue", [
    ("complete", None), ("missing-one", "缺少指定頁面"), ("only-one", "缺少指定頁面"),
    ("empty", "meta_description"), ("duplicate", "重複交付"),
    ("similar-url", "不在本批清單"), ("urls-only", "有效 url"), ("empty-final", "無法讀取"),
    ("same-title", "修訂後的標題仍重複"),
    ("industrial", None),
])
def test_six_page_handoff_and_qa_of_delivered_revision(tmp_path, monkeypatch, scenario, expected_issue):
    cli = CliRunner()
    site = tmp_path / "site"
    site.mkdir()
    pages = [f"/part-{i}.html" for i in range(1, 7)]
    for page in pages:
        (site / page[1:]).write_text(
            '<html><head><title>Parts</title><meta name="description" content="Order"></head>'
            f'<body><h1>{page}</h1></body></html>', encoding="utf-8"
        )
    audit = tmp_path / "audit"
    result = cli.invoke(app, ["audit", "consultant", "--source", str(site), "--out", str(audit)])
    assert result.exit_code == 0, result.output
    report = read_json(audit / "report.json")
    duplicates = next(f for f in report["findings"] if "TITLE_DUPLICATE" in f["id"])
    assert set(duplicates["affected_urls"]) == set(pages)
    report["findings"] = [duplicates]
    report["top_findings"] = [duplicates["id"]]
    source = tmp_path / "duplicate-titles.json"
    source.write_text(json.dumps(report), encoding="utf-8")
    seen = []

    def respond(request):
        seen.append(request.messages[0].content)
        if request.response_format == "json":
            return MockProvider().complete(request).text
        if len(seen) == 3:
            return json.dumps([{"url": pages[0], "title": "初稿"}])
        rows = [{"url": url, "title": f"{url} 規格", "meta_description": f"了解 {url} 的尺寸。",
                 "h1": f"{url} 的尺寸"} for url in pages]
        if scenario == "missing-one":
            rows.pop()
        elif scenario == "only-one":
            rows = rows[:1]
        elif scenario == "empty":
            rows[-1]["meta_description"] = "  "
        elif scenario == "duplicate":
            rows.append(rows[-1])
        elif scenario == "similar-url":
            rows[-1]["url"] += "?lang=en"
        elif scenario == "urls-only":
            rows = pages
        elif scenario == "empty-final":
            return ""
        elif scenario == "same-title":
            rows[-1]["title"] = "  " + rows[0]["title"].upper() + "  "
        elif scenario == "industrial":
            rows[0].update(title="Gear heat treatment", h1="Hardening", meta_description="Compare alloy dimensions.")
            rows[1].update(title="Patient monitor pole-mount bracket", h1="Adapter", meta_description="Check hole spacing.")
        return "```json\n" + json.dumps(rows, ensure_ascii=False) + "\n```"

    monkeypatch.setattr("seo_advisor.cli.create_provider", lambda *a, **kw: MockProvider(respond))
    out = tmp_path / "writer"
    result = cli.invoke(app, [
        "write", "--from-report", str(source), "--llm-provider", "mock",
        "--brand-context", "型錄 R7：限 A63", "--auto-revise", "--out", str(out),
    ])
    assert result.exit_code == (2 if expected_issue else 0), result.output
    assert len(seen) == 6
    assert all("型錄 R7" in prompt and all(p in prompt for p in pages) for prompt in seen)
    final = (out / "draft.md").read_text(encoding="utf-8")
    meta = read_json(out / "content-report.json")
    assert final == meta["revised_markdown"] and final in seen[-1]
    assert set(meta["request"]["metadata_batch_urls"]) == set(pages)
    assert not meta["initial_qa"]["passed"] and meta["qa"]["passed"] == (expected_issue is None)
    if expected_issue:
        assert any(x["category"] == "metadata_batch" and expected_issue in x["description"] for x in meta["qa"]["issues"])
    assert "修訂稿" in (out / "content-report.md").read_text(encoding="utf-8")


def test_article_revision_rechecks_h1_and_preserves_initial_qa(tmp_path, monkeypatch):
    calls = []

    def respond(request):
        calls.append(request)
        if request.response_format == "json":
            return MockProvider().complete(request).text
        return "## 初稿缺主標" if len(calls) == 3 else "# 修訂後的文章\n請查閱規格。"

    monkeypatch.setattr("seo_advisor.cli.create_provider", lambda *a, **kw: MockProvider(respond))
    result = CliRunner().invoke(app, ["write", "--topic", "規格指南", "--llm-provider", "mock",
                                       "--auto-revise", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    meta = read_json(tmp_path / "content-report.json")
    assert meta["request"]["metadata_batch_urls"] == []
    assert any("H1" in issue["description"] for issue in meta["initial_qa"]["issues"])
    assert meta["qa"]["passed"] and not meta["qa"]["issues"]
    assert (tmp_path / "draft.md").read_text(encoding="utf-8").startswith("# 修訂後的文章")


def test_high_roas_is_not_labeled_low_return_in_cli_report(tmp_path, monkeypatch):
    row = AnalyticsMetricRow(channel="B2B", sessions=80, conversions=1,
                             cost_minor_units=100000, revenue_minor_units=100000000)
    monkeypatch.setattr(MockAnalyticsProvider, "fetch_metrics", lambda *args: [row])
    result = CliRunner().invoke(app, ["growth", "analytics", "--provider", "mock", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    report = read_json(tmp_path / "analytics-report.json")
    findings = [f for f in report["findings"] if f["category"] == "spend"]
    assert len(findings) == 1 and findings[0]["severity"] == "P3"
    assert findings[0]["evidence"]["roas"] == 1000
    text = (tmp_path / "analytics-report.md").read_text(encoding="utf-8")
    assert "樣本較少" in text and "回報偏低" not in text
