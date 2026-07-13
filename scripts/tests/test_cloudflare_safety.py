import pytest

from seo_advisor.security.cloudflare_safety import (
    InvalidZoneIdError,
    UnsafeRedirectRuleError,
    validate_redirect_source_path,
    validate_redirect_target_url,
    validate_zone_id,
)


class TestValidateZoneId:
    def test_accepts_valid_32_hex(self):
        validate_zone_id("0123456789abcdef0123456789abcdef")  # 不拋例外即通過

    def test_rejects_uppercase(self):
        with pytest.raises(InvalidZoneIdError):
            validate_zone_id("0123456789ABCDEF0123456789ABCDEF")

    def test_rejects_wrong_length(self):
        with pytest.raises(InvalidZoneIdError):
            validate_zone_id("abc123")

    def test_rejects_path_injection_attempt(self):
        with pytest.raises(InvalidZoneIdError):
            validate_zone_id("../../../etc/passwd")

    def test_rejects_non_hex_characters(self):
        with pytest.raises(InvalidZoneIdError):
            validate_zone_id("zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz")


class TestValidateRedirectSourcePath:
    def test_accepts_simple_absolute_path(self):
        validate_redirect_source_path("/old-page")

    def test_rejects_relative_path(self):
        with pytest.raises(UnsafeRedirectRuleError):
            validate_redirect_source_path("old-page")

    def test_rejects_query_string(self):
        with pytest.raises(UnsafeRedirectRuleError):
            validate_redirect_source_path("/old-page?ref=x")

    def test_rejects_fragment(self):
        with pytest.raises(UnsafeRedirectRuleError):
            validate_redirect_source_path("/old-page#section")

    def test_rejects_unsafe_characters(self):
        with pytest.raises(UnsafeRedirectRuleError):
            validate_redirect_source_path("/old page with spaces")


class TestValidateRedirectTargetUrl:
    _allowed = frozenset({"example.com", "www.example.com"})

    def test_accepts_https_apex(self):
        validate_redirect_target_url("https://example.com/new-page", allowed_hosts=self._allowed)

    def test_accepts_https_www(self):
        validate_redirect_target_url("https://www.example.com/new-page", allowed_hosts=self._allowed)

    def test_rejects_http_scheme(self):
        with pytest.raises(UnsafeRedirectRuleError):
            validate_redirect_target_url("http://example.com/new-page", allowed_hosts=self._allowed)

    def test_rejects_userinfo(self):
        with pytest.raises(UnsafeRedirectRuleError):
            validate_redirect_target_url(
                "https://user:pass@example.com/new-page", allowed_hosts=self._allowed
            )

    def test_rejects_out_of_zone_domain(self):
        """redirect 目標不在授權網域內：避免 connector 被用來建立開放
        重導攻擊完全無關的第三方網站。"""
        with pytest.raises(UnsafeRedirectRuleError):
            validate_redirect_target_url(
                "https://totally-different-site.com/x", allowed_hosts=self._allowed
            )

    def test_rejects_missing_hostname(self):
        with pytest.raises(UnsafeRedirectRuleError):
            validate_redirect_target_url("https:///no-host", allowed_hosts=self._allowed)
