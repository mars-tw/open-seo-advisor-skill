"""Exercise ZIP auditing, reviewed repairs, local document identity and rollback."""

import json
import shlex
import subprocess
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from bs4 import BeautifulSoup
from typer.testing import CliRunner

from seo_advisor.cli import app
from seo_advisor.connectors.local_archive import LocalArchiveConnector

ORIGIN = "https://shop.example"
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def run(args):
    return CliRunner().invoke(app, list(map(str, args)), terminal_width=350)


def read(path):
    return json.loads(path.read_bytes())


def page(title, head="", body=""):
    return (
        f"<html><head><title>{title}</title>{head}</head><body><h1>{title}</h1>{body}</body></html>"
    )


def prepare_map(path, alternates=None, targets=None):
    path.write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "id": "gear",
                        "alternates": alternates
                        or {"zh-Hant": ORIGIN + "/tw", "en": ORIGIN + "/en"},
                        "targets": {"zh-Hant": "index.html"} if targets is None else targets,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def reviewed(args):
    preview = run(args)
    assert preview.exit_code == 0, preview.output
    # Execute the same argv the operator sees, including the selected review directory.
    printed = preview.output.rsplit("seo-advisor fix ", 1)[-1].strip()
    command = ["fix", *shlex.split(printed)]
    out = Path(command[command.index("--out") + 1]).resolve()
    return out, command


def rollback(source, out):
    backup = Path(read(out / "fix-result.json")["backup_id"])
    args = ["fix", "rollback", "--source", source, "--backup", backup]
    assert run(args).exit_code == 0
    assert run([*args, "--apply", "--confirm", "ROLLBACK " + backup.name]).exit_code == 0


def test_zip_audit_then_fix_then_audit_preserves_repair_and_zip(tmp_path, monkeypatch):
    staging = tmp_path / "temporary"
    staging.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(staging))
    archive = tmp_path / "export.zip"
    original = page("Gear").encode()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("index.html", original)
    archive_bytes = archive.read_bytes()
    extraction = tmp_path / "export_extracted"
    audit_args = ["audit", "consultant", "--source", archive, "--out", tmp_path / "report"]
    assert run(audit_args).exit_code == 0
    assert not extraction.exists() and not list(staging.iterdir())
    out, apply = reviewed(
        [
            "fix",
            "hreflang-html",
            "--source",
            archive,
            "--map",
            prepare_map(tmp_path / "map.json"),
            "--out",
            tmp_path / "fix",
        ]
    )
    assert run(apply).exit_code == 0
    fixed = (extraction / "index.html").read_bytes()
    assert len(BeautifulSoup(fixed, "lxml").select("link[hreflang]")) == 2
    assert run(audit_args).exit_code == 0
    assert (extraction / "index.html").read_bytes() == fixed
    rollback(extraction, out)
    assert (extraction / "index.html").read_bytes() == original
    (extraction / "index.html").write_bytes(b"<title>Owner's working copy</title>")
    assert run(audit_args).exit_code == 0
    assert (extraction / "index.html").read_bytes() == b"<title>Owner's working copy</title>"
    assert archive.read_bytes() == archive_bytes and not list(staging.iterdir())


def test_parallel_zip_readers_and_failed_extraction_are_isolated(tmp_path, monkeypatch):
    staging = tmp_path / "temporary"
    staging.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(staging))
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("index.html", "<title>Shop</title>")
    previous = tmp_path / "export_extracted"
    previous.mkdir()
    (previous / "index.html").write_text("owner", encoding="utf-8")
    with LocalArchiveConnector(str(archive)) as one, LocalArchiveConnector(str(archive)) as two:
        assert one.root != two.root and one.root != previous and two.root != previous
    archive.write_bytes(b"Incomplete ZIP")
    assert (
        run(["audit", "consultant", "--source", archive, "--out", tmp_path / "report"]).exit_code
        != 0
    )
    assert (previous / "index.html").read_text() == "owner"
    assert not list(staging.iterdir())


def test_zip_fix_keeps_legacy_unmarked_directory(tmp_path):
    archive = tmp_path / "client.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("index.html", page("Archived"))
    previous = tmp_path / "client_extracted"
    previous.mkdir()
    owner = previous / "index.html"
    owner.write_bytes(b"owner revision")
    out, apply = reviewed(
        [
            "fix",
            "hreflang-html",
            "--source",
            archive,
            "--map",
            prepare_map(tmp_path / "map.json"),
            "--out",
            tmp_path / "fix",
        ]
    )
    assert run(apply).exit_code == 0
    (new_copy,) = tmp_path.glob("client_extracted_*")
    assert (
        len(BeautifulSoup((new_copy / "index.html").read_bytes(), "lxml").select("link[hreflang]"))
        == 2
    )
    assert owner.read_bytes() == b"owner revision"
    rollback(new_copy, out)
    assert (new_copy / "index.html").read_text("utf-8") == page("Archived")


def test_local_php_without_http_reports_runtime_uncertainty(tmp_path):
    site = tmp_path / "php"
    site.mkdir()
    (site / "index.php").write_text("<?php echo 'Catalog';", encoding="utf-8")
    output = tmp_path / "report"
    result = run(["audit", "consultant", "--source", site, "--out", output])
    report = read(output / "report.json")
    assert result.exit_code == 2 and report["site_health_score"] is None
    assert report["scan_stats"]["runtime_required_urls"] == ["/"]
    assert not any(
        "HTTP_ERRORS" in f["id"] or "FETCH_FAILED" in f["id"] for f in report["findings"]
    )


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def verify_default_git(root, mode, monkeypatch):
    site = root / "repo"
    site.mkdir()
    (site / "index.html").write_text(page("Gear"), encoding="utf-8")
    git(site, "init", "-q", "-b", "main")
    git(site, "config", "user.name", "Fixture")
    git(site, "config", "user.email", "qa@example.test")
    git(site, "config", "commit.gpgsign", "false")
    git(site, "add", "index.html")
    git(site, "commit", "-qm", "Fixture")
    before = git(site, "rev-parse", "main")
    with monkeypatch.context() as context:
        context.chdir(site)
        args = ["fix", mode, "--source", ".", "--write-mode", "git-branch"]
        if mode == "engineer":
            args += ["--finding-id", "SEO-SITEMAP_MISSING-001", "--site-url", ORIGIN]
        else:
            args += ["--map", prepare_map(root / "map.json")]
        out, apply = reviewed(args)
        status = git(site, "status", "--porcelain")
        assert (out / "fix-plan.json").is_file() and status == ""
        applied = run(apply)
        assert applied.exit_code == 0, (applied.output, apply)
        branch = git(site, "branch", "--show-current")
        assert branch != "main" and git(site, "status", "--porcelain") == ""
        assert git(site, "rev-parse", "main") == before
        changed = git(site, "diff", "--name-only", "main..HEAD")
        git(site, "switch", "-q", "main")
        assert git(site, "status", "--porcelain") == ""
    return {
        "preview": 0,
        "apply": 0,
        "review_directory": out.relative_to(site).as_posix(),
        "worktree_after_preview": status,
        "branch": branch,
        "main_unchanged": True,
        "committed_file": changed,
        "preview_args": [str(value).replace(str(root), "$FIXTURE") for value in args],
        "emitted_apply_args": [str(value).replace(str(root), "$FIXTURE") for value in apply],
    }


@pytest.mark.parametrize("mode", ["engineer", "hreflang-html", "hreflang-sitemap"])
def test_default_git_repair_uses_clean_worktree(tmp_path, monkeypatch, mode):
    result = verify_default_git(tmp_path, mode, monkeypatch)
    assert result["committed_file"] == ("index.html" if mode == "hreflang-html" else "sitemap.xml")


def test_local_url_identity_and_written_sitemap(tmp_path):
    site = tmp_path / "site"
    (site / "catalog").mkdir(parents=True)
    variants = [
        "/catalog/",
        "/catalog/index.html?ref=nav",
        "/catalog/?utm_source=email",
        "/catalog/?lang=en",
        "/catalog/?lang=de",
        "/齒 輪.html",
        "/%E9%BD%92%20%E8%BC%AA.html",
        "/%2Fnot-a-directory",
    ]
    (site / "index.html").write_text(
        page("Home", body="".join(f'<a href="{u}">Details</a>' for u in variants)), encoding="utf-8"
    )
    (site / "catalog/index.html").write_text(page("Catalog"), encoding="utf-8")
    (site / "齒 輪.html").write_text(page("Gear"), encoding="utf-8")
    (site / "~catalog.html").write_text(
        page("Tilde", '<link rel="canonical" href="/%7ecatalog.html">'), encoding="utf-8"
    )
    (site / "private.html").write_text(page("Members"), encoding="utf-8")
    (site / "robots.txt").write_text(
        "User-agent: Googlebot\nDisallow: /private.html", encoding="utf-8"
    )
    audit = tmp_path / "audit"
    assert run(["audit", "consultant", "--source", site, "--out", audit]).exit_code == 0
    report = read(audit / "report.json")
    assert report["scan_stats"]["html_pages"] == 5
    assert not any("TITLE_DUPLICATE" in item["id"] for item in report["findings"])
    runtime = report["scan_stats"]["runtime_required_urls"]
    assert "/catalog/index.html?lang=en" in runtime and "/catalog/index.html?lang=de" in runtime
    out, apply = reviewed(
        [
            "fix",
            "engineer",
            "--source",
            site,
            "--finding-id",
            "SEO-SITEMAP_MISSING-001",
            "--site-url",
            ORIGIN,
            "--out",
            tmp_path / "fix",
        ]
    )
    assert run(apply).exit_code == 0
    urls = [node.text for node in ET.parse(site / "sitemap.xml").findall(f"{NS}url/{NS}loc")]
    assert sorted(urls) == sorted(
        ORIGIN + p
        for p in [
            "/index.html",
            "/catalog/index.html",
            "/~catalog.html",
            "/%E9%BD%92%20%E8%BC%AA.html",
        ]
    )
    assert any(
        "/private.html" in note and "Googlebot" in note
        for note in read(out / "fix-plan.json")["warnings"]
    )
    rollback(site, out)
    assert not (site / "sitemap.xml").exists()


def test_hreflang_sitemap_encodes_urls_and_preserves_query_delimiters(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    before = f'<urlset xmlns="{NS[1:-1]}"><url><loc>{ORIGIN}/齒 輪.html</loc><lastmod>2026-10-01</lastmod></url></urlset>'.encode()
    (site / "sitemap.xml").write_bytes(before)
    alts = {
        "zh-Hant": ORIGIN + "/齒 輪.html",
        "en": ORIGIN + "/p?q=a%26b",
        "de": ORIGIN + "/p?q=a&b",
    }
    out, apply = reviewed(
        [
            "fix",
            "hreflang-sitemap",
            "--source",
            site,
            "--map",
            prepare_map(tmp_path / "map.json", alts, {}),
            "--out",
            tmp_path / "fix",
        ]
    )
    assert run(apply).exit_code == 0
    root = ET.parse(site / "sitemap.xml")
    urls = [node.text for node in root.findall(f"{NS}url/{NS}loc")]
    assert set(urls) == {ORIGIN + "/%E9%BD%92%20%E8%BC%AA.html", alts["en"], alts["de"]}
    assert len(urls) == 3 and root.find(f"{NS}url/{NS}lastmod").text == "2026-10-01"
    assert {
        node.get("href") for node in root.findall(".//{http://www.w3.org/1999/xhtml}link")
    } == set(urls)
    rollback(site, out)
    assert (site / "sitemap.xml").read_bytes() == before


def test_big5_real_declaration_isolated_from_old_markup(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    source = page(
        "台灣供應商",
        '<!-- retired: <meta charset="utf-8"> --><script>var demo=\'<meta charset="utf-8">\';</script><meta charset = "big5">',
        "齒輪報價",
    ).encode("big5")
    target = site / "index.html"
    target.write_bytes(source)
    out, apply = reviewed(
        [
            "fix",
            "hreflang-html",
            "--source",
            site,
            "--map",
            prepare_map(tmp_path / "map.json"),
            "--out",
            tmp_path / "fix",
        ]
    )
    assert run(apply).exit_code == 0
    soup = BeautifulSoup(target.read_bytes(), "lxml")
    assert soup.title.get_text() == "台灣供應商" and "齒輪報價" in soup.body.get_text()
    assert soup.find("meta", charset=True)["charset"] == "utf-8"
    rollback(site, out)
    assert target.read_bytes() == source
