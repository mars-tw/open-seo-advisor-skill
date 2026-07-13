import zipfile
from pathlib import Path

import pytest

from seo_advisor.plugins.generator import PluginOutputExistsError, generate_plugin_scaffold
from seo_advisor.plugins.models import PluginScaffoldRequest


def _request(**overrides) -> PluginScaffoldRequest:
    kwargs = dict(
        feature="schema-generator",
        plugin_name="Open SEO Schema Helper",
        slug="open-seo-schema-helper",
        description="Adds Organization/WebSite/Article JSON-LD.",
        author="Open SEO Advisor",
    )
    kwargs.update(overrides)
    return PluginScaffoldRequest(**kwargs)


def _check_braces_balanced(content: str) -> bool:
    return content.count("{") == content.count("}") and content.count("(") == content.count(")")


class TestGeneratePluginScaffold:
    def test_writes_expected_files(self, tmp_path):
        result = generate_plugin_scaffold(_request(), out_dir=str(tmp_path))
        plugin_dir = Path(result.plugin_dir)
        assert (plugin_dir / "open-seo-schema-helper.php").exists()
        assert (plugin_dir / "includes" / "class-open-seo-schema-helper-schema.php").exists()
        assert (plugin_dir / "admin" / "class-open-seo-schema-helper-admin.php").exists()
        assert (plugin_dir / "readme.txt").exists()
        assert (plugin_dir / "uninstall.php").exists()

    def test_all_php_files_start_with_open_tag_and_balanced_braces(self, tmp_path):
        result = generate_plugin_scaffold(_request(), out_dir=str(tmp_path))
        plugin_dir = Path(result.plugin_dir)
        php_files = list(plugin_dir.rglob("*.php"))
        assert len(php_files) == 4
        for php_file in php_files:
            content = php_file.read_text(encoding="utf-8")
            assert content.startswith("<?php")
            assert _check_braces_balanced(content), f"unbalanced braces in {php_file}"

    def test_all_php_files_guard_against_direct_access(self, tmp_path):
        """每個 PHP 檔案都應該有 ABSPATH 或 WP_UNINSTALL_PLUGIN 這類防
        直接存取的守衛，避免在沒有 WordPress 執行環境時曝露邏輯。"""
        result = generate_plugin_scaffold(_request(), out_dir=str(tmp_path))
        plugin_dir = Path(result.plugin_dir)
        for php_file in plugin_dir.rglob("*.php"):
            content = php_file.read_text(encoding="utf-8")
            assert "ABSPATH" in content or "WP_UNINSTALL_PLUGIN" in content

    def test_admin_php_has_capability_check_and_nonce(self, tmp_path):
        result = generate_plugin_scaffold(_request(), out_dir=str(tmp_path))
        admin_content = (
            Path(result.plugin_dir) / "admin" / "class-open-seo-schema-helper-admin.php"
        ).read_text(encoding="utf-8")
        assert "current_user_can( 'manage_options' )" in admin_content
        assert "check_admin_referer(" in admin_content
        assert "wp_nonce_field(" in admin_content

    def test_admin_php_sanitizes_all_input(self, tmp_path):
        result = generate_plugin_scaffold(_request(), out_dir=str(tmp_path))
        admin_content = (
            Path(result.plugin_dir) / "admin" / "class-open-seo-schema-helper-admin.php"
        ).read_text(encoding="utf-8")
        assert "sanitize_text_field(" in admin_content
        assert "esc_url_raw(" in admin_content
        assert "$_POST[" in admin_content
        # 每個從 $_POST 讀取的地方都應該被 sanitize/esc 函式包住，不是裸讀取
        assert "wp_unslash(" in admin_content

    def test_schema_php_uses_wp_json_encode_not_manual_concat(self, tmp_path):
        result = generate_plugin_scaffold(_request(), out_dir=str(tmp_path))
        schema_content = (
            Path(result.plugin_dir) / "includes" / "class-open-seo-schema-helper-schema.php"
        ).read_text(encoding="utf-8")
        assert "wp_json_encode(" in schema_content
        assert "json_encode(" not in schema_content.replace("wp_json_encode(", "")

    def test_uninstall_php_has_constant_guard(self, tmp_path):
        result = generate_plugin_scaffold(_request(), out_dir=str(tmp_path))
        uninstall_content = (Path(result.plugin_dir) / "uninstall.php").read_text(encoding="utf-8")
        assert "WP_UNINSTALL_PLUGIN" in uninstall_content
        assert "delete_option(" in uninstall_content

    def test_creates_zip_by_default(self, tmp_path):
        result = generate_plugin_scaffold(_request(), out_dir=str(tmp_path))
        assert result.zip_path is not None
        assert Path(result.zip_path).exists()

    def test_zip_contains_only_slug_prefixed_relative_paths(self, tmp_path):
        result = generate_plugin_scaffold(_request(), out_dir=str(tmp_path))
        with zipfile.ZipFile(result.zip_path) as zf:
            names = zf.namelist()
            assert all(name.startswith("open-seo-schema-helper/") for name in names)
            assert all(".." not in name for name in names)
            assert not any(Path(name).is_absolute() for name in names)

    def test_no_zip_when_disabled(self, tmp_path):
        result = generate_plugin_scaffold(_request(zip_output=False), out_dir=str(tmp_path))
        assert result.zip_path is None

    def test_refuses_to_overwrite_existing_nonempty_output_without_force(self, tmp_path):
        generate_plugin_scaffold(_request(), out_dir=str(tmp_path))
        with pytest.raises(PluginOutputExistsError):
            generate_plugin_scaffold(_request(), out_dir=str(tmp_path))

    def test_force_allows_overwrite(self, tmp_path):
        generate_plugin_scaffold(_request(), out_dir=str(tmp_path))
        result = generate_plugin_scaffold(_request(), out_dir=str(tmp_path), force=True)
        assert Path(result.plugin_dir).exists()

    def test_metadata_appears_in_generated_files(self, tmp_path):
        result = generate_plugin_scaffold(
            _request(plugin_name="My Custom Plugin", author="Jane Doe"), out_dir=str(tmp_path)
        )
        main_content = Path(result.plugin_dir, "open-seo-schema-helper.php").read_text(encoding="utf-8")
        assert "My Custom Plugin" in main_content
        assert "Jane Doe" in main_content
