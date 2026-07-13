import pytest
from pydantic import ValidationError

from seo_advisor.plugins.models import (
    InvalidPluginRequestError,
    PluginScaffoldRequest,
    slug_to_php_class_prefix,
    slug_to_php_constant_prefix,
    validate_metadata_text,
    validate_slug,
)


def _base_kwargs(**overrides) -> dict:
    kwargs = dict(feature="schema-generator", plugin_name="Test Plugin", slug="test-plugin")
    kwargs.update(overrides)
    return kwargs


class TestValidateSlug:
    def test_accepts_valid_slug(self):
        assert validate_slug("open-seo-schema-helper") == "open-seo-schema-helper"

    @pytest.mark.parametrize(
        "slug",
        [
            "Open-SEO",  # 大寫
            "-open-seo",  # 開頭連字號
            "open-seo-",  # 結尾連字號
            "op",  # 太短
            "open--seo",  # 連續連字號
            "open_seo",  # 底線
            "open seo",  # 空白
            "1open",  # 數字開頭
            "",
        ],
    )
    def test_rejects_invalid_slug(self, slug):
        with pytest.raises(InvalidPluginRequestError):
            validate_slug(slug)

    def test_rejects_too_long_slug(self):
        with pytest.raises(InvalidPluginRequestError):
            validate_slug("a" + "-b" * 40)


class TestSlugConversion:
    def test_php_class_prefix(self):
        assert slug_to_php_class_prefix("open-seo-schema-helper") == "Open_Seo_Schema_Helper"

    def test_php_constant_prefix(self):
        assert slug_to_php_constant_prefix("open-seo-schema-helper") == "OPEN_SEO_SCHEMA_HELPER"


class TestValidateMetadataText:
    def test_accepts_normal_text(self):
        assert validate_metadata_text("A normal description.", field_name="description") == "A normal description."

    def test_rejects_docblock_terminator(self):
        with pytest.raises(InvalidPluginRequestError):
            validate_metadata_text("evil */ <?php system($_GET['c']); ?>", field_name="description")

    def test_rejects_php_open_tag(self):
        with pytest.raises(InvalidPluginRequestError):
            validate_metadata_text("<?php echo 1; ?>", field_name="description")

    def test_rejects_short_php_open_tag(self):
        with pytest.raises(InvalidPluginRequestError):
            validate_metadata_text("<?= 1 ?>", field_name="description")

    def test_rejects_php_close_tag(self):
        """縱深防禦：目前沒有模板把 metadata 值放進已開啟的 PHP context，
        但仍拒絕 '?>'，避免未來新增模板時不小心讓這個值提前結束 PHP 區塊。"""
        with pytest.raises(InvalidPluginRequestError):
            validate_metadata_text("normal text ?> evil", field_name="description")

    def test_rejects_newline(self):
        with pytest.raises(InvalidPluginRequestError):
            validate_metadata_text("line1\nline2", field_name="description")

    def test_rejects_carriage_return(self):
        with pytest.raises(InvalidPluginRequestError):
            validate_metadata_text("line1\rline2", field_name="description")

    def test_rejects_too_long_text(self):
        with pytest.raises(InvalidPluginRequestError):
            validate_metadata_text("a" * 201, field_name="description")


class TestPluginScaffoldRequest:
    def test_accepts_valid_request(self):
        req = PluginScaffoldRequest(**_base_kwargs())
        assert req.slug == "test-plugin"
        assert req.php_class_prefix == "Test_Plugin"
        assert req.text_domain == "test-plugin"

    def test_rejects_invalid_slug(self):
        with pytest.raises(ValidationError):
            PluginScaffoldRequest(**_base_kwargs(slug="Invalid Slug"))

    def test_rejects_unsupported_cms(self):
        with pytest.raises(ValidationError):
            PluginScaffoldRequest(**_base_kwargs(cms="drupal"))

    def test_rejects_empty_plugin_name(self):
        with pytest.raises(ValidationError):
            PluginScaffoldRequest(**_base_kwargs(plugin_name="   "))

    def test_rejects_docblock_injection_in_plugin_name(self):
        with pytest.raises(ValidationError):
            PluginScaffoldRequest(**_base_kwargs(plugin_name='Evil */ <?php system($_GET["c"]); ?>'))

    def test_rejects_docblock_injection_in_description(self):
        with pytest.raises(ValidationError):
            PluginScaffoldRequest(**_base_kwargs(description="*/ evil"))

    def test_rejects_docblock_injection_in_author(self):
        with pytest.raises(ValidationError):
            PluginScaffoldRequest(**_base_kwargs(author="*/ evil"))

    def test_default_values(self):
        req = PluginScaffoldRequest(**_base_kwargs())
        assert req.cms == "wordpress"
        assert req.version == "0.1.0"
        assert req.license == "GPL-2.0-or-later"
        assert req.zip_output is True
