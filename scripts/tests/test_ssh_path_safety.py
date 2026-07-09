"""ssh_path_safety 測試：component-wise walk 是否真的能擋下 symlink jail
escape（這是 NORA×Grok 交叉審查裡最關鍵的一項要求）。"""

import stat

import pytest

from seo_advisor.security.ssh_path_safety import (
    RemotePathNotFoundError,
    UnsafeRemotePathError,
    ensure_remote_root_allowed,
    resolve_remote_path,
    split_and_validate_components,
)


class _FakeAttr:
    def __init__(self, mode: int, size: int = 0):
        self.st_mode = mode
        self.st_size = size


class _FakeSFTP:
    """模擬 paramiko SFTPClient：用一個 dict 記錄每個絕對路徑對應的
    (mode, size)，讓測試可以精確控制哪個路徑是目錄/檔案/symlink。
    """

    def __init__(self, entries: dict[str, _FakeAttr]):
        self._entries = entries

    def lstat(self, path: str) -> _FakeAttr:
        if path not in self._entries:
            raise FileNotFoundError(path)
        return self._entries[path]


_DIR = stat.S_IFDIR | 0o755
_FILE = stat.S_IFREG | 0o644
_LINK = stat.S_IFLNK | 0o777


# --- split_and_validate_components ---


def test_split_rejects_dot_dot():
    with pytest.raises(UnsafeRemotePathError, match=r"\.\."):
        split_and_validate_components("../etc/passwd")


def test_split_rejects_dot_dot_in_middle():
    with pytest.raises(UnsafeRemotePathError, match=r"\.\."):
        split_and_validate_components("blog/../../etc/passwd")


def test_split_rejects_null_byte():
    with pytest.raises(UnsafeRemotePathError):
        split_and_validate_components("a\x00b")


def test_split_rejects_backslash():
    with pytest.raises(UnsafeRemotePathError):
        split_and_validate_components("a\\b")


def test_split_ignores_empty_and_dot_components():
    assert split_and_validate_components("a//./b/") == ["a", "b"]


def test_split_normal_path():
    assert split_and_validate_components("blog/index.html") == ["blog", "index.html"]


# --- resolve_remote_path: 正常情況 ---


def test_resolve_normal_file():
    sftp = _FakeSFTP({
        "/var/www/site/robots.txt": _FakeAttr(_FILE, size=42),
    })
    result = resolve_remote_path(sftp, "/var/www/site", "robots.txt")
    assert result.path == "robots.txt"
    assert result.is_dir is False
    assert result.size == 42


def test_resolve_nested_path():
    sftp = _FakeSFTP({
        "/var/www/site/blog": _FakeAttr(_DIR),
        "/var/www/site/blog/index.html": _FakeAttr(_FILE, size=100),
    })
    result = resolve_remote_path(sftp, "/var/www/site", "blog/index.html")
    assert result.path == "blog/index.html"
    assert result.size == 100


# --- resolve_remote_path: symlink jail escape 防護（核心安全測試） ---


def test_resolve_rejects_symlink_at_final_component():
    """最終目標本身是 symlink：拒絕。"""
    sftp = _FakeSFTP({
        "/var/www/site/secret-link": _FakeAttr(_LINK),
    })
    with pytest.raises(UnsafeRemotePathError, match="symlink"):
        resolve_remote_path(sftp, "/var/www/site", "secret-link")


def test_resolve_rejects_symlink_in_middle_component():
    """核心測試：路徑中間的目錄本身是 symlink（例如 blog 指向 /etc）。
    如果實作只對「組合後的完整路徑」做一次 lstat，這個情境會被誤判為
    安全（因為看到的是 symlink *目標* /etc/passwd 的 regular file 資訊，
    不是 symlink 本身）。component-wise walk 必須在累加到 "blog" 這一步
    時就偵測到它是 symlink 並立刻拒絕，不繼續往下解析 "passwd"。
    """
    sftp = _FakeSFTP({
        # "blog" 這個中間節點本身是 symlink（指向 /etc，但這裡不需要真的
        # 模擬 symlink target，因為 walk 應該在偵測到 symlink 當下就停止，
        # 根本不會去查 "blog/passwd" 這個路徑）。
        "/var/www/site/blog": _FakeAttr(_LINK),
    })
    with pytest.raises(UnsafeRemotePathError, match="symlink"):
        resolve_remote_path(sftp, "/var/www/site", "blog/passwd")


def test_resolve_does_not_query_beyond_symlink():
    """驗證 walk 偵測到中間節點是 symlink 後立刻停止，不會繼續查詢
    symlink 之後的路徑（避免依賴 symlink target 是否存在於 fake sftp
    entries 裡才能通過測試——即使 target 沒有任何資料，也該在更早的
    地方就被拒絕）。"""
    sftp = _FakeSFTP({
        "/var/www/site/blog": _FakeAttr(_LINK),
        # 故意不提供 "/var/www/site/blog/passwd" 這個 entry：
        # 如果實作錯誤地嘗試查詢它，會得到 FileNotFoundError 而非
        # UnsafeRemotePathError，測試會失敗，藉此驗證真的是在 symlink
        # 那一步就擋下，而不是後面查不到才報錯。
    })
    with pytest.raises(UnsafeRemotePathError, match="symlink"):
        resolve_remote_path(sftp, "/var/www/site", "blog/passwd")


def test_resolve_rejects_deeply_nested_symlink():
    """symlink 藏在更深層（第三層）也要被擋下，不是只檢查第一層。"""
    sftp = _FakeSFTP({
        "/var/www/site/a": _FakeAttr(_DIR),
        "/var/www/site/a/b": _FakeAttr(_LINK),
    })
    with pytest.raises(UnsafeRemotePathError, match="symlink"):
        resolve_remote_path(sftp, "/var/www/site", "a/b/c/d.html")


def test_resolve_rejects_when_middle_component_is_file_not_dir():
    sftp = _FakeSFTP({
        "/var/www/site/a": _FakeAttr(_FILE),
    })
    with pytest.raises(RemotePathNotFoundError):
        resolve_remote_path(sftp, "/var/www/site", "a/b.html")


def test_resolve_raises_not_found_for_missing_path():
    sftp = _FakeSFTP({})
    with pytest.raises(RemotePathNotFoundError):
        resolve_remote_path(sftp, "/var/www/site", "does-not-exist.html")


def test_resolve_rejects_dot_dot_before_touching_sftp():
    """".." 應該在語法層就被拒絕，根本不呼叫 sftp.lstat。"""
    sftp = _FakeSFTP({})  # 空的，如果程式碼呼叫 lstat 會直接 FileNotFoundError
    with pytest.raises(UnsafeRemotePathError, match=r"\.\."):
        resolve_remote_path(sftp, "/var/www/site", "../../etc/passwd")


# --- ensure_remote_root_allowed ---


@pytest.mark.parametrize("root", ["/", "/var", "/home", "/etc", "/usr", "/opt", "/root"])
def test_ensure_remote_root_rejects_forbidden_roots(root):
    with pytest.raises(UnsafeRemotePathError):
        ensure_remote_root_allowed(root)


def test_ensure_remote_root_allows_project_directory():
    ensure_remote_root_allowed("/var/www/my-site")  # 不應拋出例外
