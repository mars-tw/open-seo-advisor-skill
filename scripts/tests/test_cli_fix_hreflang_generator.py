"""`seo-advisor fix hreflang-html` / `hreflang-sitemap` 的 CLI 整合測試。"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from seo_advisor.cli import app

runner = CliRunner()


def _write_map(tmp_path, clusters: list[dict]) -> str:
    path = tmp_path / "map.json"
    path.write_text(json.dumps({"clusters": clusters}), encoding="utf-8")
    return str(path)


def _basic_cluster(targets: dict | None = None) -> dict:
    return {
        "id": "home",
        "alternates": {
            "zh-TW": "https://example.com/zh/",
            "en": "https://example.com/en/",
            "x-default": "https://example.com/",
        },
        "targets": targets or {},
    }


class TestHreflangHtmlCli:
    def test_dry_run_shows_plan_and_diff(self, tmp_path):
        site = tmp_path / "site"
        (site / "en").mkdir(parents=True)
        (site / "en" / "index.html").write_text(
            '<html><head><link rel="canonical" href="https://example.com/en/"></head><body>Hi</body></html>',
            encoding="utf-8",
        )
        map_file = _write_map(tmp_path, [_basic_cluster({"en": "en/index.html"})])

        result = runner.invoke(
            app,
            [
                "fix", "hreflang-html",
                "--source", str(site),
                "--map", map_file,
                "--out", str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 0
        assert "dry-run" in result.stdout
        assert "hreflang" in result.stdout
        assert not (site / "en" / "index.html").read_text(encoding="utf-8").count("hreflang=")

    def test_apply_without_confirm_is_rejected(self, tmp_path):
        site = tmp_path / "site"
        (site / "en").mkdir(parents=True)
        (site / "en" / "index.html").write_text("<html><head></head><body>Hi</body></html>", encoding="utf-8")
        map_file = _write_map(tmp_path, [_basic_cluster({"en": "en/index.html"})])

        result = runner.invoke(
            app,
            [
                "fix", "hreflang-html",
                "--source", str(site),
                "--map", map_file,
                "--apply",
                "--out", str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 1
        assert "確認字串" in result.stdout

    def test_apply_with_confirm_writes_file(self, tmp_path):
        site = tmp_path / "site"
        (site / "en").mkdir(parents=True)
        target = site / "en" / "index.html"
        target.write_text("<html><head></head><body>Hi</body></html>", encoding="utf-8")
        map_file = _write_map(tmp_path, [_basic_cluster({"en": "en/index.html"})])

        runner.invoke(
            app,
            ["fix", "hreflang-html", "--source", str(site), "--map", map_file, "--out", str(tmp_path / "out")],
        )
        plan_id = json.loads((tmp_path / "out" / "fix-plan.json").read_text(encoding="utf-8"))["plan_id"]

        apply_result = runner.invoke(
            app,
            [
                "fix", "hreflang-html",
                "--source", str(site),
                "--map", map_file,
                "--apply",
                "--confirm", f"APPLY {plan_id}",
                "--out", str(tmp_path / "out"),
            ],
        )
        assert apply_result.exit_code == 0
        assert "已套用" in apply_result.stdout
        assert 'hreflang="en"' in target.read_text(encoding="utf-8")

    def test_invalid_map_file_rejected_with_clear_message(self, tmp_path):
        site = tmp_path / "site"
        site.mkdir()
        map_file = tmp_path / "bad-map.json"
        map_file.write_text("{}", encoding="utf-8")

        result = runner.invoke(
            app,
            ["fix", "hreflang-html", "--source", str(site), "--map", str(map_file), "--out", str(tmp_path / "out")],
        )
        assert result.exit_code == 1
        assert "語言對照表" in result.stdout

    def test_cluster_without_targets_is_plan_only(self, tmp_path):
        site = tmp_path / "site"
        site.mkdir()
        map_file = _write_map(tmp_path, [_basic_cluster()])

        result = runner.invoke(
            app,
            ["fix", "hreflang-html", "--source", str(site), "--map", map_file, "--out", str(tmp_path / "out")],
        )
        assert result.exit_code == 0
        assert "建議" in result.stdout
        plan = json.loads((tmp_path / "out" / "fix-plan.json").read_text(encoding="utf-8"))
        assert plan["plan_only"] is True


class TestHreflangSitemapCli:
    def test_dry_run_creates_new_sitemap_preview(self, tmp_path):
        site = tmp_path / "site"
        site.mkdir()
        map_file = _write_map(tmp_path, [_basic_cluster()])

        result = runner.invoke(
            app,
            [
                "fix", "hreflang-sitemap",
                "--source", str(site),
                "--map", map_file,
                "--out", str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 0
        assert "dry-run" in result.stdout
        assert not (site / "sitemap.xml").exists()

    def test_apply_with_confirm_writes_sitemap(self, tmp_path):
        site = tmp_path / "site"
        site.mkdir()
        map_file = _write_map(tmp_path, [_basic_cluster()])

        runner.invoke(
            app,
            ["fix", "hreflang-sitemap", "--source", str(site), "--map", map_file, "--out", str(tmp_path / "out")],
        )
        plan_id = json.loads((tmp_path / "out" / "fix-plan.json").read_text(encoding="utf-8"))["plan_id"]

        apply_result = runner.invoke(
            app,
            [
                "fix", "hreflang-sitemap",
                "--source", str(site),
                "--map", map_file,
                "--apply",
                "--confirm", f"APPLY {plan_id}",
                "--out", str(tmp_path / "out"),
            ],
        )
        assert apply_result.exit_code == 0
        sitemap_content = (site / "sitemap.xml").read_text(encoding="utf-8")
        assert "xhtml:link" in sitemap_content
        assert 'hreflang="zh-TW"' in sitemap_content

    def test_existing_sitemap_index_degrades_to_plan_only(self, tmp_path):
        site = tmp_path / "site"
        site.mkdir()
        (site / "sitemap.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<sitemap><loc>https://example.com/sitemap1.xml</loc></sitemap>"
            "</sitemapindex>",
            encoding="utf-8",
        )
        map_file = _write_map(tmp_path, [_basic_cluster()])

        result = runner.invoke(
            app,
            ["fix", "hreflang-sitemap", "--source", str(site), "--map", map_file, "--out", str(tmp_path / "out")],
        )
        assert result.exit_code == 0
        assert "建議" in result.stdout
