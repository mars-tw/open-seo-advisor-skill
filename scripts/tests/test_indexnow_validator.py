import pytest

from seo_advisor.indexnow.validator import (
    IndexNowScope,
    InvalidIndexNowScopeError,
    is_url_in_scope,
)


def _scope(key_location: str) -> IndexNowScope:
    return IndexNowScope.from_key_location(key_location)


class TestIndexNowScopeFromKeyLocation:
    def test_root_key_location(self):
        scope = _scope("https://example.com/abc123.txt")
        assert scope.host == "example.com"
        assert scope.path_prefix == ""

    def test_subdirectory_key_location(self):
        scope = _scope("https://example.com/blog/abc123.txt")
        assert scope.path_prefix == "/blog"

    def test_rejects_userinfo(self):
        with pytest.raises(InvalidIndexNowScopeError):
            _scope("https://user:pass@example.com/key.txt")

    def test_rejects_missing_host(self):
        with pytest.raises(InvalidIndexNowScopeError):
            _scope("https:///key.txt")


class TestIsUrlInScope:
    def test_accepts_same_host_url(self):
        scope = _scope("https://example.com/abc123.txt")
        assert is_url_in_scope("https://example.com/post-1", scope) is True

    def test_accepts_www_apex_pair(self):
        scope = _scope("https://example.com/abc123.txt")
        assert is_url_in_scope("https://www.example.com/post-1", scope) is True

    def test_rejects_different_host(self):
        scope = _scope("https://example.com/abc123.txt")
        assert is_url_in_scope("https://evil.com/post-1", scope) is False

    def test_rejects_arbitrary_subdomain(self):
        scope = _scope("https://example.com/abc123.txt")
        assert is_url_in_scope("https://evil.example.com/post-1", scope) is False

    def test_rejects_scheme_downgrade(self):
        scope = _scope("https://example.com/abc123.txt")
        assert is_url_in_scope("http://example.com/post-1", scope) is False

    def test_rejects_fragment(self):
        scope = _scope("https://example.com/abc123.txt")
        assert is_url_in_scope("https://example.com/post-1#section", scope) is False

    def test_accepts_query_string(self):
        """IndexNow 官方範例本身就包含帶 query 的 URL，不應被拒絕
        （與 WordPressAPIConnector 的 scope 驗證刻意不同之處）。"""
        scope = _scope("https://example.com/abc123.txt")
        assert is_url_in_scope("https://example.com/post-1?ref=email", scope) is True

    def test_rejects_userinfo_in_candidate(self):
        scope = _scope("https://example.com/abc123.txt")
        assert is_url_in_scope("https://user:pass@example.com/post-1", scope) is False

    def test_non_root_key_location_restricts_to_subdirectory(self):
        """key 檔案放在 /blog/ 下時，只有 /blog/... 底下的 URL 算在授權
        範圍內，這是 IndexNow 協定對非 root keyLocation 的既有規則。"""
        scope = _scope("https://example.com/blog/abc123.txt")
        assert is_url_in_scope("https://example.com/blog/post-1", scope) is True
        assert is_url_in_scope("https://example.com/shop/item-1", scope) is False

    def test_non_root_key_location_rejects_sibling_path_prefix_bypass(self):
        """/blog 授權範圍下，"/blogevil/..." 不可被裸 startswith 誤放行。"""
        scope = _scope("https://example.com/blog/abc123.txt")
        assert is_url_in_scope("https://example.com/blogevil/post", scope) is False

    def test_rejects_dot_dot_path_traversal(self):
        scope = _scope("https://example.com/blog/abc123.txt")
        assert is_url_in_scope("https://example.com/blog/../admin", scope) is False
