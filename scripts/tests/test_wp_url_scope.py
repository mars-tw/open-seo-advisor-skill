"""security/wp_url_scope.py 的測試：REST link 的 scope allowlist 驗證。

核心情境是 NORA×Grok 雙模型交叉辯論（WordPressAPIConnector 設計）中，Grok
明確要求必須用測試鎖住的 bypass 案例：path prefix 裸 startswith 誤放行、
www/apex 遞迴剝除誤判、子網域被誤當同站、scheme/port 降級。
"""

from __future__ import annotations

import pytest

from seo_advisor.security.wp_url_scope import (
    InvalidWordPressUrlError,
    WordPressScope,
    is_url_in_scope,
)


def _scope(base_url: str) -> WordPressScope:
    return WordPressScope.from_base_url(base_url)


class TestWordPressScopeFromBaseUrl:
    def test_root_site(self):
        scope = _scope("https://example.com")
        assert scope.scheme == "https"
        assert scope.host == "example.com"
        assert scope.port == 443
        assert scope.path_prefix == ""

    def test_subdirectory_site(self):
        scope = _scope("https://example.com/blog/")
        assert scope.path_prefix == "/blog"

    def test_explicit_port_preserved(self):
        scope = _scope("https://example.com:8443/")
        assert scope.port == 8443

    def test_rejects_non_http_scheme(self):
        with pytest.raises(InvalidWordPressUrlError):
            _scope("ftp://example.com")

    def test_rejects_userinfo(self):
        with pytest.raises(InvalidWordPressUrlError):
            _scope("https://user:pass@example.com")

    def test_rejects_missing_host(self):
        with pytest.raises(InvalidWordPressUrlError):
            _scope("https:///no-host")

    def test_host_lowercased(self):
        scope = _scope("https://EXAMPLE.com")
        assert scope.host == "example.com"

    def test_trailing_dot_stripped(self):
        scope = _scope("https://example.com./")
        assert scope.host == "example.com"


class TestIsUrlInScopeBasic:
    def test_exact_match(self):
        scope = _scope("https://example.com")
        assert is_url_in_scope("https://example.com/post-1", scope) is True

    def test_different_host_rejected(self):
        scope = _scope("https://example.com")
        assert is_url_in_scope("https://evil.com/post-1", scope) is False

    def test_scheme_downgrade_rejected(self):
        """https 站不可以被導去抓 http 版本，避免 Basic Auth 明文降級。"""
        scope = _scope("https://example.com")
        assert is_url_in_scope("http://example.com/post-1", scope) is False

    def test_scheme_upgrade_also_rejected(self):
        scope = _scope("http://example.com")
        assert is_url_in_scope("https://example.com/post-1", scope) is False

    def test_javascript_scheme_rejected(self):
        scope = _scope("https://example.com")
        assert is_url_in_scope("javascript:alert(1)", scope) is False

    def test_data_scheme_rejected(self):
        scope = _scope("https://example.com")
        assert is_url_in_scope("data:text/html,evil", scope) is False

    def test_file_scheme_rejected(self):
        scope = _scope("https://example.com")
        assert is_url_in_scope("file:///etc/passwd", scope) is False

    def test_userinfo_in_candidate_rejected(self):
        scope = _scope("https://example.com")
        assert is_url_in_scope("https://user:pass@example.com/post-1", scope) is False

    def test_no_hostname_rejected(self):
        scope = _scope("https://example.com")
        assert is_url_in_scope("https:///post-1", scope) is False

    def test_malformed_url_rejected(self):
        scope = _scope("https://example.com")
        assert is_url_in_scope("http://[invalid", scope) is False


class TestWwwApexPair:
    def test_apex_authorized_www_candidate_allowed(self):
        scope = _scope("https://example.com")
        assert is_url_in_scope("https://www.example.com/post-1", scope) is True

    def test_www_authorized_apex_candidate_allowed(self):
        scope = _scope("https://www.example.com")
        assert is_url_in_scope("https://example.com/post-1", scope) is True

    def test_double_www_not_treated_as_pair(self):
        """www.www.example.com 不可被誤判等於 example.com（不遞迴剝除）。"""
        scope = _scope("https://example.com")
        assert is_url_in_scope("https://www.www.example.com/post-1", scope) is False

    def test_arbitrary_subdomain_rejected(self):
        """evil.example.com 不算 example.com 的子網域授權。"""
        scope = _scope("https://example.com")
        assert is_url_in_scope("https://evil.example.com/post-1", scope) is False

    def test_suffix_match_not_treated_as_same_host(self):
        """notexample.com 不可被誤判等於 example.com（避免用 endswith 誤判）。"""
        scope = _scope("https://example.com")
        assert is_url_in_scope("https://notexample.com/post-1", scope) is False

    def test_prefix_domain_not_treated_as_same_host(self):
        scope = _scope("https://example.com")
        assert is_url_in_scope("https://example.com.evil.com/post-1", scope) is False


class TestPortHandling:
    def test_default_https_port_matches_explicit_443(self):
        scope = _scope("https://example.com")
        assert is_url_in_scope("https://example.com:443/post-1", scope) is True

    def test_non_default_port_mismatch_rejected(self):
        scope = _scope("https://example.com")
        assert is_url_in_scope("https://example.com:8080/post-1", scope) is False

    def test_explicit_port_scope_requires_match(self):
        scope = _scope("https://example.com:8443")
        assert is_url_in_scope("https://example.com/post-1", scope) is False
        assert is_url_in_scope("https://example.com:8443/post-1", scope) is True


class TestPathPrefixScope:
    def test_root_scope_allows_any_path(self):
        scope = _scope("https://example.com")
        assert is_url_in_scope("https://example.com/anything/deep/path", scope) is True

    def test_subdirectory_exact_match(self):
        scope = _scope("https://example.com/blog")
        assert is_url_in_scope("https://example.com/blog", scope) is True
        assert is_url_in_scope("https://example.com/blog/", scope) is True

    def test_subdirectory_nested_path_allowed(self):
        scope = _scope("https://example.com/blog")
        assert is_url_in_scope("https://example.com/blog/2024/post-1", scope) is True

    def test_sibling_path_with_shared_prefix_rejected(self):
        """/blog 授權範圍下，"/blogevil/..." 不可被裸 startswith 誤放行。"""
        scope = _scope("https://example.com/blog")
        assert is_url_in_scope("https://example.com/blogevil/post", scope) is False

    def test_dash_suffix_sibling_rejected(self):
        scope = _scope("https://example.com/blog")
        assert is_url_in_scope("https://example.com/blog-backup/post", scope) is False

    def test_unrelated_path_rejected(self):
        scope = _scope("https://example.com/blog")
        assert is_url_in_scope("https://example.com/shop/item", scope) is False

    def test_dot_dot_segment_rejected(self):
        scope = _scope("https://example.com/blog")
        assert is_url_in_scope("https://example.com/blog/../admin", scope) is False

    def test_encoded_dot_dot_segment_rejected(self):
        """%2e%2e 這種編碼過的 ".." 必須在 decode 之後才判斷，不能被繞過。"""
        scope = _scope("https://example.com/blog")
        assert is_url_in_scope("https://example.com/blog/%2e%2e/admin", scope) is False

    def test_single_dot_segment_ignored(self):
        scope = _scope("https://example.com/blog")
        assert is_url_in_scope("https://example.com/blog/./post-1", scope) is True

    def test_query_and_fragment_not_part_of_path_check(self):
        scope = _scope("https://example.com/blog")
        assert is_url_in_scope("https://example.com/blog/post-1?ref=x#top", scope) is True

    def test_null_byte_rejected(self):
        scope = _scope("https://example.com/blog")
        assert is_url_in_scope("https://example.com/blog/post\x00", scope) is False
