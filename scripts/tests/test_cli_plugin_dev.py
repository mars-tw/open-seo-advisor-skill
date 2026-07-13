"""`seo-advisor plugin dev ...` 的 CLI 整合測試。"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from seo_advisor.cli import app

runner = CliRunner()

_BASE_ARGS = [
    "plugin", "dev",
    "--cms", "wordpress",
    "--feature", "schema-generator",
    "--name", "Open SEO Schema Helper",
    "--slug", "open-seo-schema-helper",
]


class TestPluginDevCli:
    def test_generates_scaffold_successfully(self, tmp_path):
        result = runner.invoke(app, [*_BASE_ARGS, "--out", str(tmp_path)])
        assert result.exit_code == 0
        assert "完成" in result.stdout
        plugin_dir = tmp_path / "open-seo-schema-helper"
        assert (plugin_dir / "open-seo-schema-helper.php").exists()
        assert (plugin_dir.parent / "open-seo-schema-helper.zip").exists()

    def test_no_zip_flag_skips_zip(self, tmp_path):
        result = runner.invoke(app, [*_BASE_ARGS, "--no-zip", "--out", str(tmp_path)])
        assert result.exit_code == 0
        assert not (tmp_path / "open-seo-schema-helper.zip").exists()

    def test_invalid_slug_rejected_with_exit_code_1(self, tmp_path):
        args = [
            "plugin", "dev",
            "--cms", "wordpress",
            "--feature", "schema-generator",
            "--name", "Test",
            "--slug", "Bad Slug",
            "--out", str(tmp_path),
        ]
        result = runner.invoke(app, args)
        assert result.exit_code == 1
        assert "參數不合法" in result.stdout

    def test_unsupported_feature_rejected(self, tmp_path):
        args = [
            "plugin", "dev",
            "--cms", "wordpress",
            "--feature", "internal-linking",
            "--name", "Test",
            "--slug", "test-plugin",
            "--out", str(tmp_path),
        ]
        result = runner.invoke(app, args)
        assert result.exit_code == 1

    def test_unsupported_cms_rejected(self, tmp_path):
        args = [
            "plugin", "dev",
            "--cms", "drupal",
            "--feature", "schema-generator",
            "--name", "Test",
            "--slug", "test-plugin",
            "--out", str(tmp_path),
        ]
        result = runner.invoke(app, args)
        assert result.exit_code == 1

    def test_second_run_without_force_is_rejected(self, tmp_path):
        first = runner.invoke(app, [*_BASE_ARGS, "--out", str(tmp_path)])
        assert first.exit_code == 0
        second = runner.invoke(app, [*_BASE_ARGS, "--out", str(tmp_path)])
        assert second.exit_code == 1
        assert "--force" in second.stdout

    def test_force_allows_regeneration(self, tmp_path):
        first = runner.invoke(app, [*_BASE_ARGS, "--out", str(tmp_path)])
        assert first.exit_code == 0
        second = runner.invoke(app, [*_BASE_ARGS, "--force", "--out", str(tmp_path)])
        assert second.exit_code == 0

    def test_docblock_injection_attempt_rejected(self, tmp_path):
        args = [
            "plugin", "dev",
            "--cms", "wordpress",
            "--feature", "schema-generator",
            "--name", 'Evil */ <?php system($_GET["c"]); ?>',
            "--slug", "test-plugin",
            "--out", str(tmp_path),
        ]
        result = runner.invoke(app, args)
        assert result.exit_code == 1

    def test_generated_zip_does_not_leak_absolute_paths(self, tmp_path):
        import zipfile

        result = runner.invoke(app, [*_BASE_ARGS, "--out", str(tmp_path)])
        assert result.exit_code == 0
        zip_path = tmp_path / "open-seo-schema-helper.zip"
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                assert not Path(name).is_absolute()
                assert ".." not in name
