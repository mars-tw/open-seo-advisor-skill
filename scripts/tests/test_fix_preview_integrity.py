"""Exercise preview and apply through the public CLI using a real temporary site."""

import json
import zipfile
from xml.etree import ElementTree

import pytest
from bs4 import BeautifulSoup
from typer.testing import CliRunner

from seo_advisor.fixers.cli import _load_findings, fix_app
from seo_advisor.fixers.hreflang_map import parse_language_map
from seo_advisor.fixers import hreflang_sitemap
from seo_advisor.fixers.models import PatchPlan
from seo_advisor.fixers.runner import apply_plan
from seo_advisor.connectors.local_archive import LocalArchiveConnector
from seo_advisor.models import SafetyPolicy


def _run(args):
    return CliRunner().invoke(fix_app, [str(arg) for arg in args])


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "site with spaces"
    root.mkdir()
    (root / "index.html").write_text("<title>Products</title>", encoding="utf-8")
    return root


def _report(site, path):
    findings, _ = _load_findings(str(site), None, None)
    path.write_text(json.dumps({"findings": [f.model_dump(mode="json") for f in findings]}), encoding="utf-8")
    return path


@pytest.mark.parametrize(("name", "finding", "content"), [
    ("robots.txt", "ROBOTS_MISSING", "User-agent: *\nDisallow: /members/\n"),
    ("sitemap.xml", "SITEMAP_MISSING", "<urlset><url><loc>https://example.com/current</loc></url></urlset>"),
])
def test_old_missing_finding_preserves_new_file(site, tmp_path, name, finding, content):
    report = _report(site, tmp_path / "report.json")
    (site / name).write_text(content, encoding="utf-8")
    args = ["engineer", "--source", site, "--from-report", report, "--finding-id", f"SEO-{finding}-001",
            "--site-url", "https://shop.example", "--out", tmp_path / "out"]
    assert _run(args).exit_code != 0
    assert not (tmp_path / "out/fix-plan.json").exists()
    assert (site / name).read_text(encoding="utf-8") == content


def test_apply_commits_only_a_matching_reviewed_plan(site, tmp_path):
    report = _report(site, tmp_path / "prior report.json")
    out = tmp_path / "reviewed plans"
    args = ["engineer", "--source", site, "--from-report", report,
            "--finding-id", "SEO-SITEMAP_MISSING-001", "--site-url", "https://shop.example", "--out", out]
    preview = _run(args)
    assert preview.exit_code == 0, preview.stdout
    command = preview.stdout.split("seo-advisor fix engineer ")[-1]
    for option in ("--site-url", "--from-report", "--out", "--confirm"):
        assert option in command
    assert f"'{site}'" in command
    assert f"'{report}'" in command
    saved = (out / "fix-plan.json").read_bytes()
    plan = json.loads(saved)
    confirm = ["--apply", "--confirm", "APPLY " + plan["plan_id"]]
    other = tmp_path / "other source"
    other.mkdir()
    (other / "index.html").write_bytes((site / "index.html").read_bytes())
    assert _run([other if x == site else x for x in args] + confirm).exit_code != 0
    assert not (other / "sitemap.xml").exists()
    assert _run(["https://another.example" if x == "https://shop.example" else x for x in args] + confirm).exit_code != 0
    (site / "extra.html").write_text("<title>Another page</title>", encoding="utf-8")
    assert _run(args + confirm).exit_code != 0
    assert (out / "fix-plan.json").read_bytes() == saved
    assert not (site / "sitemap.xml").exists()
    (site / "extra.html").unlink()
    (out / "fix-plan.json").write_text(json.dumps({**plan, "summary": "changed"}), encoding="utf-8")
    assert _run(args + confirm).exit_code != 0
    (out / "fix-plan.json").write_bytes(saved)
    assert _run(args + confirm).exit_code == 0
    assert (site / "sitemap.xml").read_bytes() == plan["targets"][0]["fixed_content"].encode()
    assert _run(args + confirm).exit_code != 0


def test_hreflang_preserves_big5_and_rejects_corrupted_input(site, tmp_path):
    target = site / "tw.html"
    original = '<html><head><meta charset="big5"><title>台灣供應商</title></head><body>齒輪報價</body></html>'.encode("big5")
    target.write_bytes(original)
    path = tmp_path / "map.json"
    path.write_text(json.dumps({"clusters": [{"id": "gear", "targets": {"zh-TW": "tw.html"},
                   "alternates": {"zh-TW": "https://shop.example/tw", "en": "https://shop.example/en"}}]}))
    out = tmp_path / "preview"
    args = ["hreflang-html", "--source", site, "--map", path, "--out", out]
    preview = _run(args)
    assert preview.exit_code == 0, preview.stdout
    plan = json.loads((out / "fix-plan.json").read_bytes())
    confirm = ["--apply", "--confirm", "APPLY " + plan["plan_id"]]
    target.write_bytes(original + b"\xa4")
    assert _run(args + confirm).exit_code != 0
    assert target.read_bytes() == original + b"\xa4"
    target.write_bytes(original)
    applied = _run(args + confirm)
    assert applied.exit_code == 0, applied.stdout
    soup = BeautifulSoup(target.read_bytes(), "lxml")
    assert soup.title.get_text() == "台灣供應商"
    assert soup.body.get_text() == "齒輪報價"
    assert soup.find("meta")["charset"].lower() == "utf-8"
    assert soup.find("link", hreflang="en")


def test_canonical_disagreement_requires_a_decision(site, tmp_path):
    (site / "index.html").write_text('<head><link rel="canonical" href="/old"><link rel="canonical" href="/"></head>')
    args = ["engineer", "--source", site, "--finding-id", "SEO-CANONICAL_CONFLICT-001",
            "--site-url", "https://shop.example", "--out", tmp_path / "out"]
    preview = _run(args)
    assert preview.exit_code == 0, preview.stdout
    plan = json.loads((tmp_path / "out/fix-plan.json").read_bytes())
    assert plan["plan_only"] and not plan["targets"]
    assert "https://shop.example/old" in plan["suggested_actions"][0]
    assert "HTTP" in plan["suggested_actions"][0]


def test_generated_sitemap_uses_google_indexable_canonical_urls(site, tmp_path):
    (site / "preview.html").write_text('<head><meta name="googlebot" content="none"></head>')
    (site / "duplicate.html").write_text('<head><link rel="canonical" href="/index.html"></head>')
    (site / "index.html").write_text('<head><link rel="canonical" href="/"></head>')
    args = ["engineer", "--source", site, "--finding-id", "SEO-SITEMAP_MISSING-001",
            "--site-url", "https://shop.example", "--out", tmp_path / "out"]
    result = _run(args)
    assert result.exit_code == 0, result.stdout
    plan = json.loads((tmp_path / "out/fix-plan.json").read_bytes())
    sitemap = ElementTree.fromstring(plan["targets"][0]["fixed_content"])
    assert [loc.text for loc in sitemap.findall(".//{*}loc")] == ["https://shop.example/"]


def test_hreflang_limit_counts_existing_and_unique_added_urls(monkeypatch):
    monkeypatch.setattr(hreflang_sitemap, "_MAX_URLS_PER_SITEMAP", 2)
    xml = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/tw</loc></url></urlset>'
    language_map = parse_language_map({"clusters": [{"id": "gear", "alternates": {
        "zh-Hant-TW": "https://example.com/tw", "zh-Hans": "https://example.com/cn",
        "x-default": "https://example.com/tw",
    }}]})
    result = hreflang_sitemap.build_hreflang_sitemap_plan(language_map, sitemap_path="sitemap.xml", current_sitemap_xml=xml)
    assert not result.plan_only
    assert len(ElementTree.fromstring(result.targets[0].fixed_content)) == 2
    full = xml.replace("</urlset>", "<url><loc>https://example.com/other</loc></url></urlset>")
    result = hreflang_sitemap.build_hreflang_sitemap_plan(language_map, sitemap_path="sitemap.xml", current_sitemap_xml=full)
    assert result.plan_only and not result.targets


def test_zip_apply_does_not_reextract_over_owner_edits(tmp_path):
    archive = tmp_path / "demo.zip"
    original = b"User-agent: *\nDisallow: /old/\n"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("robots.txt", original)
        bundle.writestr("index.html", "<title>Welcome</title>")
    args = ["engineer", "--source", archive, "--finding-id", "SEO-ROBOTS_NO_SITEMAP-001",
            "--site-url", "https://shop.example", "--out", tmp_path / "out"]
    preview = _run(args)
    assert preview.exit_code == 0, preview.stdout
    plan = json.loads((tmp_path / "out/fix-plan.json").read_bytes())
    target = tmp_path / "demo_extracted/robots.txt"
    target.write_bytes(original + b"Disallow: /new/\n")
    confirm = ["--apply", "--confirm", "APPLY " + plan["plan_id"]]
    assert _run(args + confirm).exit_code != 0
    assert target.read_bytes() == original + b"Disallow: /new/\n"
    target.write_bytes(original)
    assert _run(args + confirm).exit_code == 0
    assert b"Sitemap: https://shop.example/sitemap.xml" in target.read_bytes()
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.read("robots.txt") == original


def test_runner_rejects_stale_batch_before_first_write(site, tmp_path):
    for name in ("tw.html", "en.html"):
        (site / name).write_bytes(b"<html><head><title>Product</title></head></html>")
    language_map = tmp_path / "map.json"
    language_map.write_text(json.dumps({"clusters": [{"id": "p", "alternates": {
        "zh-TW": "https://example.com/tw", "en": "https://example.com/en", "x-default": "https://example.com/tw"},
        "targets": {"zh-TW": "tw.html", "en": "en.html", "x-default": "tw.html"}}]}))
    out = tmp_path / "review"
    preview = _run(["hreflang-html", "--map", language_map, "--source", site, "--out", out])
    assert preview.exit_code == 0, preview.stdout
    reviewed = PatchPlan.model_validate_json((out / "fix-plan.json").read_bytes())
    assert [t.path for t in reviewed.targets] == ["tw.html", "en.html"]
    changed = site / reviewed.targets[-1].path
    changed.write_bytes(b"<title>Owner changed this page</title>")
    before = {target.path: (site / target.path).read_bytes() for target in reviewed.targets}
    policy = SafetyPolicy(dry_run=False, allowed_capabilities={"read_urls", "read_files", "write_files"})
    with pytest.raises(ValueError, match="自預覽後已變更"):
        apply_plan(reviewed, connector=LocalArchiveConnector(str(site), policy=policy))
    assert all((site / name).read_bytes() == raw for name, raw in before.items())
    assert not (site / ".seo-advisor/backups").exists()
