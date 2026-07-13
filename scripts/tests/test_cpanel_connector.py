import httpx
import pytest
import respx

from seo_advisor.connectors.cpanel import (
    CPanelAuthError,
    CPanelConnector,
    CPanelConnectorError,
)
from seo_advisor.models import SafetyPolicy
from seo_advisor.security.cpanel_path_safety import UnsafeRemotePathError

_HOST = "cpanel.example.com"
_PORT = 2083
_BASE = f"https://{_HOST}:{_PORT}"
_CONFIRM = f"CONNECT CPANEL {_HOST}:{_PORT}"


def _mock_list_files_tree(tree: dict[str, list[dict]]):
    """用單一 route + side_effect 依 `dir` 查詢參數路由到不同目錄內容，
    避免對同一個 URL 註冊多個 respx mock 時後者覆蓋前者的問題（respx
    對同一路徑的 mock 採用「最後註冊」語意，逐一呼叫 _mock_list_files
    會讓先前註冊的目錄結果全部消失）。未在 tree 裡列出的目錄回傳空清單。
    """

    def _responder(request: httpx.Request) -> httpx.Response:
        directory = request.url.params.get("dir", "")
        entries = tree.get(directory, [])
        return httpx.Response(200, json={"status": 1, "data": entries})

    respx.get(f"{_BASE}/execute/Fileman/list_files").mock(side_effect=_responder)


def _make_connector(*, tree: dict[str, list[dict]] | None = None, **kwargs) -> CPanelConnector:
    _mock_list_files_tree(tree or {"public_html": []})
    return CPanelConnector(
        _HOST, username="myuser", api_token="test-token", confirm_connect=_CONFIRM, **kwargs
    )


class TestConstructorValidation:
    def test_rejects_connection_without_confirmation(self):
        with pytest.raises(CPanelConnectorError, match="確認"):
            CPanelConnector(_HOST, username="myuser", api_token="test-token")

    def test_rejects_wrong_confirmation(self):
        with pytest.raises(CPanelConnectorError, match="確認"):
            CPanelConnector(
                _HOST, username="myuser", api_token="test-token", confirm_connect="CONNECT CPANEL wrong:2083"
            )

    def test_rejects_missing_token(self, monkeypatch):
        monkeypatch.delenv("CPANEL_API_TOKEN", raising=False)
        with pytest.raises(CPanelConnectorError, match="Token"):
            CPanelConnector(_HOST, username="myuser", confirm_connect=_CONFIRM)

    def test_rejects_forbidden_remote_root(self):
        with pytest.raises(UnsafeRemotePathError):
            CPanelConnector(
                _HOST, username="myuser", api_token="test-token",
                confirm_connect=_CONFIRM, remote_root="/",
            )

    def test_rejects_private_host_without_explicit_allow(self):
        with pytest.raises(Exception):
            CPanelConnector(
                "192.168.1.1", username="myuser", api_token="test-token",
                confirm_connect="CONNECT CPANEL 192.168.1.1:2083",
            )

    @respx.mock
    def test_rejects_invalid_token(self):
        respx.get(f"{_BASE}/execute/Fileman/list_files", params={"dir": "public_html"}).mock(
            return_value=httpx.Response(401, json={"status": 0, "errors": ["invalid token"]})
        )
        with pytest.raises(CPanelAuthError):
            CPanelConnector(_HOST, username="myuser", api_token="bad-token", confirm_connect=_CONFIRM)

    @respx.mock
    def test_accepts_valid_connection(self):
        connector = _make_connector()
        assert connector.id() == "cpanel:myuser@cpanel.example.com:2083"
        connector.close()


class TestCapabilities:
    @respx.mock
    def test_capabilities_default_read_only(self):
        connector = _make_connector()
        assert connector.capabilities() == {"read_files", "read_urls"}
        connector.close()

    @respx.mock
    def test_capabilities_include_write_when_enabled_and_policy_allows(self):
        policy = SafetyPolicy(allowed_capabilities={"read_files", "read_urls", "write_files"})
        connector = _make_connector(enable_write=True, policy=policy)
        assert connector.capabilities() == {"read_files", "read_urls", "write_files"}
        connector.close()

    @respx.mock
    def test_capabilities_exclude_write_when_enable_write_false(self):
        policy = SafetyPolicy(allowed_capabilities={"read_files", "read_urls", "write_files"})
        connector = _make_connector(enable_write=False, policy=policy)
        assert "write_files" not in connector.capabilities()
        connector.close()

    @respx.mock
    def test_write_file_requires_capability_even_when_enabled(self):
        connector = _make_connector(enable_write=True)  # policy 沒開 write_files
        with pytest.raises(PermissionError):
            connector.write_file("robots.txt", b"content", dry_run=True)
        connector.close()


class TestListFilesAndReadFile:
    @respx.mock
    def test_list_files_top_level(self):
        connector = _make_connector(tree={
            "public_html": [
                {"file": "index.html", "type": "file", "size": 100},
                {"file": "blog", "type": "dir", "size": 0},
                {"file": "sneaky-link", "type": "link", "size": 0},
            ],
        })
        records = connector.list_files("")
        names = {r.path for r in records}
        assert "index.html" in names
        assert "blog" in names
        assert "sneaky-link" not in names
        connector.close()

    @respx.mock
    def test_read_file_returns_content(self):
        connector = _make_connector(tree={
            "public_html": [{"file": "robots.txt", "type": "file", "size": 20}],
        })
        respx.get(f"{_BASE}/execute/Fileman/get_file_content").mock(
            return_value=httpx.Response(200, json={"status": 1, "data": {"content": "User-agent: *\n"}})
        )
        content = connector.read_file("robots.txt")
        assert content == b"User-agent: *\n"
        connector.close()

    @respx.mock
    def test_read_file_rejects_denylisted_filename(self):
        connector = _make_connector()
        with pytest.raises(UnsafeRemotePathError):
            connector.read_file("wp-config.php")
        connector.close()

    @respx.mock
    def test_read_file_rejects_disallowed_extension(self):
        connector = _make_connector()
        with pytest.raises(UnsafeRemotePathError):
            connector.read_file("app.py")
        connector.close()

    @respx.mock
    def test_resolve_rejects_symlink_in_middle(self):
        connector = _make_connector(tree={
            "public_html": [{"file": "blog", "type": "link", "size": 0}],
        })
        with pytest.raises(UnsafeRemotePathError):
            connector.read_file("blog/post.html")
        connector.close()


class TestListUrlsAndFetchUrl:
    @respx.mock
    def test_list_urls_recurses(self):
        connector = _make_connector(tree={
            "public_html": [
                {"file": "index.html", "type": "file", "size": 10},
                {"file": "blog", "type": "dir", "size": 0},
            ],
            "public_html/blog": [{"file": "post.html", "type": "file", "size": 20}],
        })
        records = connector.list_urls(seed="/", limit=100)
        urls = {r.url for r in records}
        assert urls == {"/index.html", "/blog/post.html"}
        connector.close()

    @respx.mock
    def test_list_urls_skips_tooling_dirs(self):
        connector = _make_connector(tree={
            "public_html": [
                {"file": "node_modules", "type": "dir", "size": 0},
                {"file": "index.html", "type": "file", "size": 10},
            ],
        })
        records = connector.list_urls(seed="/", limit=100)
        assert {r.url for r in records} == {"/index.html"}
        connector.close()

    @respx.mock
    def test_fetch_url_rejects_query_string(self):
        connector = _make_connector()
        snapshot = connector.fetch_url("/index.html?x=1")
        assert snapshot.fetch_error_type == "unsafe_remote_path"
        connector.close()

    @respx.mock
    def test_fetch_url_rejects_scheme(self):
        connector = _make_connector()
        snapshot = connector.fetch_url("http://169.254.169.254/evil")
        assert snapshot.fetch_error_type == "unsafe_remote_path"
        connector.close()

    @respx.mock
    def test_fetch_url_returns_content(self):
        connector = _make_connector(tree={
            "public_html": [{"file": "index.html", "type": "file", "size": 10}],
        })
        respx.get(f"{_BASE}/execute/Fileman/get_file_content").mock(
            return_value=httpx.Response(200, json={"status": 1, "data": {"content": "<h1>Hi</h1>"}})
        )
        snapshot = connector.fetch_url("/index.html")
        assert snapshot.status_code == 200
        assert "Hi" in snapshot.html
        connector.close()


class TestWriteFile:
    @respx.mock
    def test_dry_run_does_not_call_save_api(self):
        policy = SafetyPolicy(dry_run=True, allowed_capabilities={"read_files", "read_urls", "write_files"})
        connector = _make_connector(enable_write=True, policy=policy)
        result = connector.write_file("robots.txt", b"User-agent: *\n", dry_run=True)
        assert result.dry_run is True
        assert result.applied is False
        connector.close()

    @respx.mock
    def test_rejects_php_file(self):
        policy = SafetyPolicy(dry_run=True, allowed_capabilities={"read_files", "read_urls", "write_files"})
        connector = _make_connector(enable_write=True, policy=policy)
        with pytest.raises(UnsafeRemotePathError):
            connector.write_file("index.php", b"<?php echo 1; ?>", dry_run=True)
        connector.close()

    @respx.mock
    def test_rejects_htaccess(self):
        policy = SafetyPolicy(dry_run=True, allowed_capabilities={"read_files", "read_urls", "write_files"})
        connector = _make_connector(enable_write=True, policy=policy)
        with pytest.raises(UnsafeRemotePathError):
            connector.write_file(".htaccess", b"RewriteEngine On", dry_run=True)
        connector.close()

    @respx.mock
    def test_real_write_requires_non_dry_run_policy(self):
        policy = SafetyPolicy(dry_run=True, allowed_capabilities={"read_files", "read_urls", "write_files"})
        connector = _make_connector(enable_write=True, policy=policy)
        with pytest.raises(PermissionError):
            connector.write_file("robots.txt", b"content", dry_run=False)
        connector.close()

    @respx.mock
    def test_real_write_succeeds(self):
        policy = SafetyPolicy(
            dry_run=False, allowed_capabilities={"read_files", "read_urls", "write_files"}
        )
        connector = _make_connector(enable_write=True, policy=policy)
        save_route = respx.get(f"{_BASE}/execute/Fileman/save_file_content").mock(
            return_value=httpx.Response(200, json={"status": 1, "data": {}})
        )
        result = connector.write_file("robots.txt", b"User-agent: *\n", dry_run=False)
        assert result.applied is True
        assert save_route.called
        connector.close()

    @respx.mock
    def test_rejects_oversized_content(self):
        policy = SafetyPolicy(dry_run=True, allowed_capabilities={"read_files", "read_urls", "write_files"})
        connector = _make_connector(enable_write=True, policy=policy)
        huge_content = b"x" * (3 * 1024 * 1024)
        with pytest.raises(CPanelConnectorError):
            connector.write_file("robots.txt", huge_content, dry_run=True)
        connector.close()


class TestBackup:
    @respx.mock
    def test_backup_records_existing_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HOME", str(tmp_path))
        respx.get(f"{_BASE}/execute/Fileman/get_file_content").mock(
            return_value=httpx.Response(200, json={"status": 1, "data": {"content": "hello"}})
        )
        policy = SafetyPolicy(allowed_capabilities={"read_files", "read_urls", "write_files"})
        connector = _make_connector(
            enable_write=True, policy=policy,
            tree={"public_html": [{"file": "robots.txt", "type": "file", "size": 5}]},
        )
        result = connector.backup(["robots.txt"])
        assert result.backup_path is not None
        connector.close()

    @respx.mock
    def test_backup_dir_name_is_filesystem_safe(self, tmp_path, monkeypatch):
        """host 字串不能直接當目錄名稱使用——用安全字元子集 + hash 組合，
        避免特殊字元或大小寫碰撞問題。"""
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HOME", str(tmp_path))
        respx.get(f"{_BASE}/execute/Fileman/get_file_content").mock(
            return_value=httpx.Response(200, json={"status": 1, "data": {"content": "hello"}})
        )
        policy = SafetyPolicy(allowed_capabilities={"read_files", "read_urls", "write_files"})
        connector = _make_connector(
            enable_write=True, policy=policy,
            tree={"public_html": [{"file": "robots.txt", "type": "file", "size": 5}]},
        )
        result = connector.backup(["robots.txt"])
        backup_dir_name = result.backup_path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        assert backup_dir_name.replace("-", "").replace(".", "").isalnum()
        connector.close()


class TestListDirEntryLimit:
    @respx.mock
    def test_rejects_directory_with_too_many_entries(self):
        huge_tree = {
            "public_html": [{"file": f"f{i}.html", "type": "file", "size": 1} for i in range(5001)],
        }
        connector = _make_connector(tree=huge_tree)
        with pytest.raises(CPanelConnectorError):
            connector.list_files("")
        connector.close()


class TestRedaction:
    @respx.mock
    def test_auth_error_does_not_leak_token(self):
        respx.get(f"{_BASE}/execute/Fileman/list_files", params={"dir": "public_html"}).mock(
            return_value=httpx.Response(401, json={"status": 0, "errors": ["bad token"]})
        )
        try:
            CPanelConnector(
                _HOST, username="myuser", api_token="super-secret-value", confirm_connect=_CONFIRM
            )
        except CPanelAuthError as exc:
            assert "super-secret-value" not in str(exc)
