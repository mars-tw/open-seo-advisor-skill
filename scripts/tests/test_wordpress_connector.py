import httpx
import pytest
import respx

from seo_advisor.connectors.wordpress import (
    WordPressAPIConnector,
    WordPressAuthError,
    WordPressConnectorError,
    WordPressRestUnavailableError,
)
from seo_advisor.models import SafetyPolicy


def _policy(**overrides) -> SafetyPolicy:
    defaults = {"allowed_capabilities": {"read_urls"}}
    defaults.update(overrides)
    return SafetyPolicy(**defaults)


class TestCapabilitiesAndBasicContract:
    def test_capabilities_is_read_urls_only(self):
        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        assert connector.capabilities() == {"read_urls"}

    def test_id_does_not_contain_username(self):
        connector = WordPressAPIConnector(
            "https://example.com", username="admin", app_password="xxxx xxxx xxxx xxxx xxxx xxxx", policy=_policy()
        )
        assert connector.id() == "wordpress:example.com"
        assert "admin" not in connector.id()

    def test_write_file_not_overridden(self):
        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        with pytest.raises(NotImplementedError):
            connector.write_file("foo.html", b"data")

    def test_run_command_not_overridden(self):
        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        with pytest.raises(NotImplementedError):
            connector.run_command(["wp", "plugin", "list"])

    def test_get_logs_not_overridden(self):
        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        with pytest.raises(NotImplementedError):
            connector.get_logs("access", "2024-01-01")

    def test_read_file_not_overridden(self):
        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        with pytest.raises(NotImplementedError):
            connector.read_file("foo.html")


class TestConstructorValidation:
    def test_rejects_partial_credentials_username_only(self):
        with pytest.raises(WordPressConnectorError):
            WordPressAPIConnector("https://example.com", username="admin", policy=_policy())

    def test_rejects_partial_credentials_password_only(self):
        with pytest.raises(WordPressConnectorError):
            WordPressAPIConnector("https://example.com", app_password="xxxx xxxx xxxx xxxx xxxx xxxx", policy=_policy())

    def test_rejects_public_http(self):
        with pytest.raises(WordPressConnectorError, match="HTTPS"):
            WordPressAPIConnector("http://example.com", policy=_policy())

    def test_allows_http_with_local_dev_flags(self):
        connector = WordPressAPIConnector(
            "http://localhost:8080",
            policy=_policy(allow_private_network=True),
            allow_insecure_local_dev=True,
        )
        assert connector.id() == "wordpress:localhost"

    def test_rejects_http_with_only_allow_private_network(self):
        """allow_private_network 沒搭配 allow_insecure_local_dev 仍應拒絕明文 HTTP。"""
        with pytest.raises(WordPressConnectorError, match="HTTPS"):
            WordPressAPIConnector(
                "http://localhost:8080",
                policy=_policy(allow_private_network=True),
            )

    def test_rejects_userinfo_in_base_url(self):
        with pytest.raises(Exception):
            WordPressAPIConnector("https://user:pass@example.com", policy=_policy())

    def test_rejects_private_host_without_allow_private_network(self):
        from seo_advisor.security.network_policy import PrivateNetworkBlockedError

        with pytest.raises(PrivateNetworkBlockedError):
            WordPressAPIConnector("https://169.254.169.254", policy=_policy())


class TestProbe:
    @respx.mock
    def test_probe_detects_rest_and_namespaces(self):
        respx.get("https://example.com/wp-json/").mock(
            return_value=httpx.Response(200, json={"namespaces": ["wp/v2", "yoast/v1"]})
        )
        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        profile = connector.probe()
        assert profile.source_type == "wordpress"
        assert any("wp/v2" in note for note in profile.notes)

    @respx.mock
    def test_probe_raises_when_rest_root_404(self):
        respx.get("https://example.com/wp-json/").mock(return_value=httpx.Response(404))
        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        with pytest.raises(WordPressRestUnavailableError):
            connector.probe()

    @respx.mock
    def test_probe_raises_when_not_json(self):
        respx.get("https://example.com/wp-json/").mock(
            return_value=httpx.Response(200, text="<html>not json</html>")
        )
        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        with pytest.raises(WordPressRestUnavailableError):
            connector.probe()

    @respx.mock
    def test_probe_verifies_auth_via_posts_not_users_me(self):
        respx.get("https://example.com/wp-json/").mock(return_value=httpx.Response(200, json={}))
        posts_route = respx.get("https://example.com/wp-json/wp/v2/posts").mock(
            return_value=httpx.Response(200, json=[{"id": 1}])
        )
        users_me_route = respx.get("https://example.com/wp-json/wp/v2/users/me")

        connector = WordPressAPIConnector(
            "https://example.com",
            username="seo-audit",
            app_password="xxxx xxxx xxxx xxxx xxxx xxxx",
            policy=_policy(),
        )
        profile = connector.probe()

        assert posts_route.called
        assert not users_me_route.called
        assert any("認證有效" in note for note in profile.notes)

    @respx.mock
    def test_probe_raises_auth_error_on_401(self):
        respx.get("https://example.com/wp-json/").mock(return_value=httpx.Response(200, json={}))
        respx.get("https://example.com/wp-json/wp/v2/posts").mock(return_value=httpx.Response(401))

        connector = WordPressAPIConnector(
            "https://example.com",
            username="seo-audit",
            app_password="wrong wrong wrong wrong wrong wrong",
            policy=_policy(),
        )
        with pytest.raises(WordPressAuthError):
            connector.probe()

    @respx.mock
    def test_probe_degrades_gracefully_on_403_for_posts(self):
        respx.get("https://example.com/wp-json/").mock(return_value=httpx.Response(200, json={}))
        respx.get("https://example.com/wp-json/wp/v2/posts").mock(return_value=httpx.Response(403))

        connector = WordPressAPIConnector(
            "https://example.com",
            username="seo-audit",
            app_password="xxxx xxxx xxxx xxxx xxxx xxxx",
            policy=_policy(),
        )
        profile = connector.probe()
        assert any("無法用 posts 端點驗證" in note for note in profile.notes)


class TestRestRedirectHandling:
    @respx.mock
    def test_rest_redirect_raises_instead_of_following(self):
        respx.get("https://example.com/wp-json/").mock(
            return_value=httpx.Response(302, headers={"location": "https://attacker.example/"})
        )
        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        with pytest.raises(WordPressConnectorError, match="重新導向"):
            connector.probe()


class TestListUrls:
    @respx.mock
    def test_accepts_in_scope_links(self):
        respx.get("https://example.com/wp-json/wp/v2/posts").mock(
            return_value=httpx.Response(
                200,
                json=[
                    {"id": 1, "link": "https://example.com/post-1", "type": "post"},
                    {"id": 2, "link": "https://example.com/post-2", "type": "post"},
                ],
            )
        )
        respx.get("https://example.com/wp-json/wp/v2/pages").mock(return_value=httpx.Response(200, json=[]))

        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        records = connector.list_urls(seed="https://example.com", limit=100)

        urls = {r.url for r in records}
        assert urls == {"https://example.com/post-1", "https://example.com/post-2"}
        assert all(r.source == "wordpress_rest:post" for r in records)

    @respx.mock
    def test_rejects_out_of_scope_link_pointing_to_metadata(self):
        """REST 回傳的 link 是 attacker-controlled：即使伺服器聲稱這是合法連結，
        指向 metadata IP 的連結也絕不能進入 UrlRecord。"""
        respx.get("https://example.com/wp-json/wp/v2/posts").mock(
            return_value=httpx.Response(
                200,
                json=[{"id": 1, "link": "http://169.254.169.254/latest/meta-data/", "type": "post"}],
            )
        )
        respx.get("https://example.com/wp-json/wp/v2/pages").mock(return_value=httpx.Response(200, json=[]))

        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        records = connector.list_urls(seed="https://example.com", limit=100)

        assert records == []

    @respx.mock
    def test_rejects_out_of_scope_link_pointing_to_other_domain(self):
        respx.get("https://example.com/wp-json/wp/v2/posts").mock(
            return_value=httpx.Response(
                200,
                json=[{"id": 1, "link": "https://totally-different-site.com/post-1", "type": "post"}],
            )
        )
        respx.get("https://example.com/wp-json/wp/v2/pages").mock(return_value=httpx.Response(200, json=[]))

        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        records = connector.list_urls(seed="https://example.com", limit=100)

        assert records == []

    @respx.mock
    def test_respects_limit_cap(self):
        posts = [
            {"id": i, "link": f"https://example.com/post-{i}", "type": "post"} for i in range(1, 11)
        ]
        respx.get("https://example.com/wp-json/wp/v2/posts").mock(return_value=httpx.Response(200, json=posts))
        respx.get("https://example.com/wp-json/wp/v2/pages").mock(return_value=httpx.Response(200, json=[]))

        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        records = connector.list_urls(seed="https://example.com", limit=3)

        assert len(records) == 3

    @respx.mock
    def test_stops_pagination_early_when_short_page_returned(self):
        """回傳數量少於 per_page 代表沒有下一頁，應提早停止，不再發下一頁請求。"""
        posts_route = respx.get("https://example.com/wp-json/wp/v2/posts").mock(
            return_value=httpx.Response(
                200, json=[{"id": 1, "link": "https://example.com/post-1", "type": "post"}]
            )
        )
        respx.get("https://example.com/wp-json/wp/v2/pages").mock(return_value=httpx.Response(200, json=[]))

        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        records = connector.list_urls(seed="https://example.com", limit=250)

        assert len(records) == 1
        assert posts_route.call_count == 1

    @respx.mock
    def test_pages_route_missing_does_not_crash(self):
        respx.get("https://example.com/wp-json/wp/v2/posts").mock(
            return_value=httpx.Response(200, json=[{"id": 1, "link": "https://example.com/post-1"}])
        )
        respx.get("https://example.com/wp-json/wp/v2/pages").mock(return_value=httpx.Response(404))

        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        records = connector.list_urls(seed="https://example.com", limit=100)

        assert len(records) == 1


class TestFetchUrl:
    @respx.mock
    def test_fetch_in_scope_url_succeeds(self):
        respx.get("https://example.com/post-1").mock(
            return_value=httpx.Response(200, text="<h1>Post</h1>", headers={"content-type": "text/html"})
        )
        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        snapshot = connector.fetch_url("https://example.com/post-1")
        assert snapshot.status_code == 200
        assert "Post" in snapshot.html

    def test_fetch_out_of_scope_url_rejected_without_request(self):
        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        snapshot = connector.fetch_url("https://evil.com/post-1")
        assert snapshot.status_code == 0
        assert snapshot.fetch_error_type == "out_of_scope"

    @respx.mock
    def test_fetch_does_not_send_auth_header(self):
        route = respx.get("https://example.com/post-1").mock(
            return_value=httpx.Response(200, text="<h1>Post</h1>", headers={"content-type": "text/html"})
        )
        connector = WordPressAPIConnector(
            "https://example.com",
            username="seo-audit",
            app_password="xxxx xxxx xxxx xxxx xxxx xxxx",
            policy=_policy(),
        )
        connector.fetch_url("https://example.com/post-1")
        sent_request = route.calls[0].request
        assert "authorization" not in {k.lower() for k in sent_request.headers.keys()}

    @respx.mock
    def test_fetch_redirect_out_of_scope_stops(self):
        respx.get("https://example.com/post-1").mock(
            return_value=httpx.Response(302, headers={"location": "https://evil.com/steal"})
        )
        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        snapshot = connector.fetch_url("https://example.com/post-1")
        assert snapshot.fetch_error_type == "redirect_out_of_scope"

    @respx.mock
    def test_fetch_same_scope_redirect_followed(self):
        respx.get("https://example.com/old-url").mock(
            return_value=httpx.Response(301, headers={"location": "https://example.com/new-url"})
        )
        respx.get("https://example.com/new-url").mock(
            return_value=httpx.Response(200, text="<h1>New</h1>", headers={"content-type": "text/html"})
        )
        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        snapshot = connector.fetch_url("https://example.com/old-url")
        assert snapshot.status_code == 200
        assert "New" in snapshot.html

    def test_render_true_raises_not_implemented(self):
        connector = WordPressAPIConnector("https://example.com", policy=_policy())
        with pytest.raises(NotImplementedError):
            connector.fetch_url("https://example.com/post-1", render=True)


class TestRedaction:
    def test_redact_secrets_masks_basic_auth_header(self):
        from seo_advisor.errors import redact_secrets

        text = "request failed: Authorization: Basic c2VvLWF1ZGl0OnBhc3N3b3Jk"
        redacted = redact_secrets(text)
        assert "c2VvLWF1ZGl0OnBhc3N3b3Jk" not in redacted

    def test_redact_secrets_masks_app_password_format(self):
        from seo_advisor.errors import redact_secrets

        text = "using password xxxx abcd efgh ijkl mnop qrst for login"
        redacted = redact_secrets(text)
        assert "xxxx abcd efgh ijkl mnop qrst" not in redacted
