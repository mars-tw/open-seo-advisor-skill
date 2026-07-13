import pytest

from seo_advisor.security.cpanel_path_safety import (
    RemoteFileEntry,
    RemoteFileNotFoundError,
    UnsafeRemotePathError,
    ensure_remote_root_allowed,
    resolve_remote_path,
)


def _make_list_dir(tree: dict[str, list[RemoteFileEntry]]):
    """tree: {directory_path: [entries]}，模擬固定目錄結構。"""

    def _list_dir(directory: str) -> list[RemoteFileEntry]:
        return tree.get(directory, [])

    return _list_dir


class TestResolveRemotePath:
    def test_resolves_top_level_file(self):
        list_dir = _make_list_dir({
            "public_html": [RemoteFileEntry(path="public_html/index.html", is_dir=False, is_link=False, size=100)],
        })
        result = resolve_remote_path(list_dir, "public_html", "index.html")
        assert result.path == "index.html"
        assert result.is_dir is False

    def test_resolves_nested_file(self):
        list_dir = _make_list_dir({
            "public_html": [RemoteFileEntry(path="public_html/blog", is_dir=True, is_link=False, size=0)],
            "public_html/blog": [
                RemoteFileEntry(path="public_html/blog/post.html", is_dir=False, is_link=False, size=50)
            ],
        })
        result = resolve_remote_path(list_dir, "public_html", "blog/post.html")
        assert result.path == "blog/post.html"

    def test_rejects_symlink_at_final_component(self):
        list_dir = _make_list_dir({
            "public_html": [RemoteFileEntry(path="public_html/secret", is_dir=False, is_link=True, size=0)],
        })
        with pytest.raises(UnsafeRemotePathError):
            resolve_remote_path(list_dir, "public_html", "secret")

    def test_rejects_symlink_in_middle_component(self):
        """中間層是 symlink 也必須拒絕，不能只檢查最終目標——這是
        component-wise walk 存在的核心理由。"""
        list_dir = _make_list_dir({
            "public_html": [RemoteFileEntry(path="public_html/blog", is_dir=True, is_link=True, size=0)],
            "public_html/blog": [
                RemoteFileEntry(path="public_html/blog/post.html", is_dir=False, is_link=False, size=50)
            ],
        })
        with pytest.raises(UnsafeRemotePathError):
            resolve_remote_path(list_dir, "public_html", "blog/post.html")

    def test_raises_not_found_when_component_missing(self):
        list_dir = _make_list_dir({"public_html": []})
        with pytest.raises(RemoteFileNotFoundError):
            resolve_remote_path(list_dir, "public_html", "missing.html")

    def test_rejects_intermediate_component_not_a_directory(self):
        list_dir = _make_list_dir({
            "public_html": [RemoteFileEntry(path="public_html/notadir", is_dir=False, is_link=False, size=10)],
        })
        with pytest.raises(RemoteFileNotFoundError):
            resolve_remote_path(list_dir, "public_html", "notadir/file.html")

    def test_rejects_path_traversal(self):
        list_dir = _make_list_dir({})
        with pytest.raises(UnsafeRemotePathError):
            resolve_remote_path(list_dir, "public_html", "../../../etc/passwd")

    def test_rejects_backslash(self):
        list_dir = _make_list_dir({})
        with pytest.raises(UnsafeRemotePathError):
            resolve_remote_path(list_dir, "public_html", "blog\\post.html")

    def test_empty_path_rejected_by_split_validation(self):
        """空字串路徑由語法層驗證直接拒絕（沿用 split_and_validate_components
        的既有行為）；呼叫端若要表示「remote_root 本身」，應在呼叫
        resolve_remote_path 之前自行判斷並跳過（見 SSHConnector.list_files
        對空字串 path 的既有處理方式），不應該讓這個函式吞下空字串。"""
        list_dir = _make_list_dir({})
        with pytest.raises(UnsafeRemotePathError):
            resolve_remote_path(list_dir, "public_html", "")


class TestEnsureRemoteRootAllowed:
    def test_accepts_public_html(self):
        ensure_remote_root_allowed("public_html")  # 不拋例外即通過

    def test_accepts_nested_subdirectory(self):
        ensure_remote_root_allowed("public_html/subsite")

    def test_rejects_empty_root(self):
        with pytest.raises(UnsafeRemotePathError):
            ensure_remote_root_allowed("")

    def test_rejects_home_directory(self):
        with pytest.raises(UnsafeRemotePathError):
            ensure_remote_root_allowed("home")

    def test_rejects_slash(self):
        with pytest.raises(UnsafeRemotePathError):
            ensure_remote_root_allowed("/")
