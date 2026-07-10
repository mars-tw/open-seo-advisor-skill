"""SSHConnector 測試：連線前的安全閘門（網段檢查、確認字串）、讀取白名單/
denylist、capabilities() 誠實回報。真實 SSH/SFTP 連線用 mock 模擬，不依賴
真實伺服器；連線前的 DNS 解析/socket 建立也一併 mock，避免測試碰觸真實
網路（見 _resolve_and_verify_host 的 DNS TOCTOU 修法：只解析一次 DNS，
用解析出的 IP 直接建立 socket 再交給 paramiko）。"""

from unittest.mock import MagicMock, patch

import pytest

from seo_advisor.connectors.base import ConnectorCapabilityError
from seo_advisor.connectors.ssh import SSHConnector, SSHConnectorError, _is_read_target_allowed
from seo_advisor.security.ssh_path_safety import UnsafeRemotePathError


def _make_mock_client(remote_root_real: str = "/var/www/site"):
    """建立一個 mock paramiko.SSHClient，connect() 成功、open_sftp() 回傳
    一個可控制 normalize() 結果的 mock sftp。"""
    mock_client = MagicMock()
    mock_sftp = MagicMock()
    mock_sftp.normalize.return_value = remote_root_real
    mock_client.open_sftp.return_value = mock_sftp
    return mock_client, mock_sftp


def _patch_dns_resolves_to_public_ip(mock_getaddrinfo, mock_socket_class, ip: str = "93.184.216.34"):
    """模擬 socket.getaddrinfo 解析出一個公開 IP，且該 IP 的 socket 連線
    立即成功（不做任何真實網路操作）。"""
    mock_getaddrinfo.return_value = [(2, 1, 6, "", (ip, 22))]
    mock_socket_instance = MagicMock()
    mock_socket_class.return_value = mock_socket_instance
    return mock_socket_instance


# --- 連線前的網段檢查（在任何 DNS 解析/paramiko 呼叫之前就該擋下，
# 這些情境本身就是字面 IP 或已知會被拒絕的名稱，不需要真的解析網路） ---


def test_rejects_cloud_metadata_host_before_connecting():
    with pytest.raises(SSHConnectorError, match="metadata"):
        SSHConnector(
            "169.254.169.254", user="deploy", remote_root="/var/www/site",
            confirm_connect="CONNECT 169.254.169.254:22",
        )


def test_rejects_private_network_without_explicit_allow():
    with pytest.raises(SSHConnectorError, match="私有網段"):
        SSHConnector(
            "192.168.1.1", user="deploy", remote_root="/var/www/site",
            confirm_connect="CONNECT 192.168.1.1:22",
        )


def test_rejects_localhost_without_explicit_allow():
    with pytest.raises(SSHConnectorError, match="私有網段"):
        SSHConnector(
            "localhost", user="deploy", remote_root="/var/www/site",
            confirm_connect="CONNECT localhost:22",
        )


# --- 連線確認字串 ---


@patch("socket.socket")
@patch("socket.getaddrinfo")
def test_rejects_connection_without_confirmation(mock_getaddrinfo, mock_socket_class):
    with pytest.raises(SSHConnectorError, match="明確確認"):
        SSHConnector("example.com", user="deploy", remote_root="/var/www/site")
    # 核心斷言（Grok 複審抓到的順序問題）：確認字串驗證必須在任何網路
    # 操作（DNS 解析、TCP 連線）之前完成，不該對目標主機發送任何封包
    # 才發現使用者根本沒有確認授權。
    mock_getaddrinfo.assert_not_called()
    mock_socket_class.assert_not_called()


@patch("socket.socket")
@patch("socket.getaddrinfo")
def test_rejects_connection_with_wrong_confirmation(mock_getaddrinfo, mock_socket_class):
    with pytest.raises(SSHConnectorError, match="明確確認"):
        SSHConnector(
            "example.com", user="deploy", remote_root="/var/www/site",
            confirm_connect="CONNECT wrong-host.com:22",
        )
    mock_getaddrinfo.assert_not_called()
    mock_socket_class.assert_not_called()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_accepts_connection_with_correct_confirmation(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    mock_client, mock_sftp = _make_mock_client()
    mock_paramiko.SSHClient.return_value = mock_client
    mock_paramiko.ssh_exception.SSHException = Exception
    _patch_dns_resolves_to_public_ip(mock_getaddrinfo, mock_socket_class)

    connector = SSHConnector(
        "example.com", user="deploy", remote_root="/var/www/site",
        confirm_connect="CONNECT example.com:22",
    )
    assert connector.id() == "ssh:deploy@example.com:22"
    connector.close()


# --- DNS TOCTOU 防護：解析出的 IP 若是私網/metadata 也要擋下 ---


@patch("socket.socket")
@patch("socket.getaddrinfo")
def test_rejects_when_dns_resolves_hostname_to_private_ip(mock_getaddrinfo, mock_socket_class):
    """即使輸入的是一個看似公開的 hostname，若 DNS 解析出的 IP 落在私有
    網段，也必須拒絕——這是 DNS rebinding 防護的核心：檢查的對象是
    「解析出的 IP」，不是輸入的字串本身。"""
    _patch_dns_resolves_to_public_ip(mock_getaddrinfo, mock_socket_class, ip="10.0.0.5")
    with pytest.raises(SSHConnectorError, match="私有網段"):
        SSHConnector(
            "sneaky-rebind.example.com", user="deploy", remote_root="/var/www/site",
            confirm_connect="CONNECT sneaky-rebind.example.com:22",
        )


@patch("socket.socket")
@patch("socket.getaddrinfo")
def test_rejects_when_dns_resolves_hostname_to_metadata_ip(mock_getaddrinfo, mock_socket_class):
    _patch_dns_resolves_to_public_ip(mock_getaddrinfo, mock_socket_class, ip="169.254.169.254")
    with pytest.raises(SSHConnectorError, match="metadata"):
        SSHConnector(
            "sneaky-rebind.example.com", user="deploy", remote_root="/var/www/site",
            confirm_connect="CONNECT sneaky-rebind.example.com:22",
        )


# --- remote_root 過寬檢查 ---


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_rejects_forbidden_remote_root(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    mock_client, mock_sftp = _make_mock_client(remote_root_real="/var")
    mock_paramiko.SSHClient.return_value = mock_client
    mock_paramiko.ssh_exception.SSHException = Exception
    _patch_dns_resolves_to_public_ip(mock_getaddrinfo, mock_socket_class)

    with pytest.raises(UnsafeRemotePathError):
        SSHConnector(
            "example.com", user="deploy", remote_root="/var",
            confirm_connect="CONNECT example.com:22",
        )


# --- capabilities() 誠實回報 ---


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_capabilities_reports_read_files_and_read_urls_by_default(
    mock_paramiko, mock_getaddrinfo, mock_socket_class
):
    mock_client, mock_sftp = _make_mock_client()
    mock_paramiko.SSHClient.return_value = mock_client
    mock_paramiko.ssh_exception.SSHException = Exception
    _patch_dns_resolves_to_public_ip(mock_getaddrinfo, mock_socket_class)

    connector = SSHConnector(
        "example.com", user="deploy", remote_root="/var/www/site",
        confirm_connect="CONNECT example.com:22",
    )
    assert connector.capabilities() == {"read_files", "read_urls"}
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_capabilities_includes_read_logs_only_when_configured(
    mock_paramiko, mock_getaddrinfo, mock_socket_class
):
    mock_client, mock_sftp = _make_mock_client()
    mock_paramiko.SSHClient.return_value = mock_client
    mock_paramiko.ssh_exception.SSHException = Exception
    _patch_dns_resolves_to_public_ip(mock_getaddrinfo, mock_socket_class)

    connector = SSHConnector(
        "example.com", user="deploy", remote_root="/var/www/site",
        confirm_connect="CONNECT example.com:22",
        allowed_log_paths={"access": "/var/log/nginx/access.log"},
    )
    assert connector.capabilities() == {"read_files", "read_urls", "read_logs"}
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_write_file_and_run_command_are_not_implemented(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    """write_file()/run_command() 完全不 override，維持 base class 的
    NotImplementedError——這是 NORA×Grok 定案要求的「不做半套實作」。"""
    mock_client, mock_sftp = _make_mock_client()
    mock_paramiko.SSHClient.return_value = mock_client
    mock_paramiko.ssh_exception.SSHException = Exception
    _patch_dns_resolves_to_public_ip(mock_getaddrinfo, mock_socket_class)

    connector = SSHConnector(
        "example.com", user="deploy", remote_root="/var/www/site",
        confirm_connect="CONNECT example.com:22",
    )
    with pytest.raises(NotImplementedError):
        connector.write_file("robots.txt", b"content", dry_run=False)
    with pytest.raises(NotImplementedError):
        connector.run_command(["ls"])
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_get_logs_without_allowed_log_paths_raises_capability_error(
    mock_paramiko, mock_getaddrinfo, mock_socket_class
):
    """未設定 allowed_log_paths 時，get_logs() 應丟出 ConnectorCapabilityError
    （代表「這個 connector 實例根本沒有這個能力」），而不是先撞到
    SafetyPolicy 的 PermissionError（那個代表「policy 沒開放這個能力」，
    語意不同，使用者應該一眼看出差異）。"""
    mock_client, mock_sftp = _make_mock_client()
    mock_paramiko.SSHClient.return_value = mock_client
    mock_paramiko.ssh_exception.SSHException = Exception
    _patch_dns_resolves_to_public_ip(mock_getaddrinfo, mock_socket_class)

    connector = SSHConnector(
        "example.com", user="deploy", remote_root="/var/www/site",
        confirm_connect="CONNECT example.com:22",
    )
    with pytest.raises(ConnectorCapabilityError):
        connector.get_logs("access")
    connector.close()


# --- read allowlist / denylist ---


def test_read_target_allows_html():
    assert _is_read_target_allowed("index.html") is True
    assert _is_read_target_allowed("blog/post.html") is True


def test_read_target_rejects_conf_and_env():
    assert _is_read_target_allowed("nginx.conf") is False
    assert _is_read_target_allowed(".env") is False
    assert _is_read_target_allowed(".env.production") is False


def test_read_target_rejects_sensitive_basenames_even_with_allowed_extension():
    """即使副檔名在白名單內（.json/.txt），敏感 basename 仍要被拒絕。"""
    assert _is_read_target_allowed("secrets.json") is False
    assert _is_read_target_allowed("config.json") is False
    assert _is_read_target_allowed("credentials.txt") is False


def test_read_target_rejects_pattern_matches():
    assert _is_read_target_allowed("my-secret-data.json") is False
    assert _is_read_target_allowed("api-token-list.txt") is False


def test_read_target_rejects_second_round_denylist_additions():
    """NORA×Grok 第二輪複審補充的敏感檔名，逐一驗證都被擋下。"""
    assert _is_read_target_allowed("wp-config.txt") is False
    assert _is_read_target_allowed(".netrc") is False
    assert _is_read_target_allowed("service-account.json") is False
    assert _is_read_target_allowed("service-account-prod.json") is False
    assert _is_read_target_allowed("google-services.json") is False
    assert _is_read_target_allowed("firebase-config.json") is False
    assert _is_read_target_allowed("appsettings.json") is False
    assert _is_read_target_allowed("appsettings.production.json") is False
    assert _is_read_target_allowed("client_secret.json") is False
    assert _is_read_target_allowed("authorized_keys.txt") is False
    assert _is_read_target_allowed("known_hosts.txt") is False
    assert _is_read_target_allowed("database.json") is False


def test_read_target_does_not_overblock_legitimate_security_txt():
    """denylist 不該過於寬泛：合法的 security.txt（RFC 9116）不該被誤擋。"""
    assert _is_read_target_allowed("security.txt") is True


def test_read_target_rejects_empty_path():
    """空字串路徑（等同要求讀取 remote_root 目錄本身）沒有副檔名，必須被
    白名單擋下，讓 read_file("") 在呼叫 resolve_remote_path()/sftp 之前
    就失敗，避免拼出「讀取整個 remote_root」這種奇怪的中間狀態。"""
    assert _is_read_target_allowed("") is False


def test_read_target_allows_normal_json_and_txt():
    assert _is_read_target_allowed("manifest.json") is True
    assert _is_read_target_allowed("readme.txt") is True


# --- read_file / list_files 端到端（mock sftp） ---


class _FakeSFTPAttr:
    def __init__(self, mode, size=0, filename=""):
        self.st_mode = mode
        self.st_size = size
        self.filename = filename


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_read_file_returns_content_within_size_limit(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    import stat

    mock_client, mock_sftp = _make_mock_client()
    mock_paramiko.SSHClient.return_value = mock_client
    mock_paramiko.ssh_exception.SSHException = Exception
    _patch_dns_resolves_to_public_ip(mock_getaddrinfo, mock_socket_class)

    mock_sftp.lstat.return_value = _FakeSFTPAttr(stat.S_IFREG | 0o644, size=13)
    mock_file = MagicMock()
    mock_file.__enter__.return_value.read.return_value = b"Hello, world!"
    mock_sftp.open.return_value = mock_file

    connector = SSHConnector(
        "example.com", user="deploy", remote_root="/var/www/site",
        confirm_connect="CONNECT example.com:22",
    )
    content = connector.read_file("robots.txt")
    assert content == b"Hello, world!"
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_read_file_rejects_denylisted_filename_without_touching_sftp(
    mock_paramiko, mock_getaddrinfo, mock_socket_class
):
    mock_client, mock_sftp = _make_mock_client()
    mock_paramiko.SSHClient.return_value = mock_client
    mock_paramiko.ssh_exception.SSHException = Exception
    _patch_dns_resolves_to_public_ip(mock_getaddrinfo, mock_socket_class)

    connector = SSHConnector(
        "example.com", user="deploy", remote_root="/var/www/site",
        confirm_connect="CONNECT example.com:22",
    )
    with pytest.raises(UnsafeRemotePathError):
        connector.read_file("secrets.json")
    # 核心斷言：denylist 檢查應在呼叫任何 sftp 方法之前就擋下。
    mock_sftp.lstat.assert_not_called()
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_list_files_excludes_symlinks(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    import stat

    mock_client, mock_sftp = _make_mock_client()
    mock_paramiko.SSHClient.return_value = mock_client
    mock_paramiko.ssh_exception.SSHException = Exception
    _patch_dns_resolves_to_public_ip(mock_getaddrinfo, mock_socket_class)

    mock_sftp.listdir_attr.return_value = [
        _FakeSFTPAttr(stat.S_IFREG | 0o644, size=100, filename="index.html"),
        _FakeSFTPAttr(stat.S_IFLNK | 0o777, size=0, filename="sneaky-link"),
        _FakeSFTPAttr(stat.S_IFDIR | 0o755, size=0, filename="blog"),
    ]

    connector = SSHConnector(
        "example.com", user="deploy", remote_root="/var/www/site",
        confirm_connect="CONNECT example.com:22",
    )
    records = connector.list_files("")
    names = {r.path for r in records}
    assert "index.html" in names
    assert "blog" in names
    assert "sneaky-link" not in names
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_known_hosts_missing_raises_clear_error(
    mock_paramiko, mock_getaddrinfo, mock_socket_class, tmp_path
):
    mock_client = MagicMock()
    mock_client.load_host_keys.side_effect = FileNotFoundError()
    mock_paramiko.SSHClient.return_value = mock_client
    mock_paramiko.ssh_exception.SSHException = Exception
    _patch_dns_resolves_to_public_ip(mock_getaddrinfo, mock_socket_class)

    with pytest.raises(SSHConnectorError, match="known_hosts"):
        SSHConnector(
            "example.com", user="deploy", remote_root="/var/www/site",
            confirm_connect="CONNECT example.com:22",
            known_hosts_path=str(tmp_path / "nonexistent_known_hosts"),
        )


# --- list_urls() / fetch_url()：接進 Consultant CLI 的 read_urls 能力 ---


def _connect_ssh(mock_paramiko, mock_getaddrinfo, mock_socket_class, mock_sftp=None, **kwargs):
    from seo_advisor.models import SafetyPolicy

    mock_client, sftp = _make_mock_client()
    if mock_sftp is not None:
        mock_client.open_sftp.return_value = mock_sftp
        sftp = mock_sftp
        sftp.normalize.return_value = "/var/www/site"
    mock_paramiko.SSHClient.return_value = mock_client
    mock_paramiko.ssh_exception.SSHException = Exception
    _patch_dns_resolves_to_public_ip(mock_getaddrinfo, mock_socket_class)

    # 測試預設開通 read_files/read_urls/read_logs：這裡驗證的是 connector
    # 本身的行為（capabilities 誠實回報、log 白名單邏輯），不是
    # SafetyPolicy 的權限閘門本身（那由 test_capabilities_* 系列覆蓋）。
    kwargs.setdefault(
        "policy",
        SafetyPolicy(allowed_capabilities={"read_files", "read_urls", "read_logs"}),
    )
    connector = SSHConnector(
        "example.com", user="deploy", remote_root="/var/www/site",
        confirm_connect="CONNECT example.com:22",
        **kwargs,
    )
    return connector, sftp


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_list_urls_recurses_into_subdirectories(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    import stat

    mock_sftp = MagicMock()

    def _listdir_attr(remote_dir):
        if remote_dir == "/var/www/site":
            return [
                _FakeSFTPAttr(stat.S_IFREG | 0o644, size=10, filename="index.html"),
                _FakeSFTPAttr(stat.S_IFDIR | 0o755, size=0, filename="blog"),
            ]
        if remote_dir == "/var/www/site/blog":
            return [_FakeSFTPAttr(stat.S_IFREG | 0o644, size=20, filename="post-1.html")]
        raise FileNotFoundError(remote_dir)

    mock_sftp.listdir_attr.side_effect = _listdir_attr

    def _lstat(path):
        if path in ("/var/www/site/blog", "/var/www/site/blog/post-1.html", "/var/www/site/index.html"):
            mode = stat.S_IFDIR | 0o755 if path.endswith("blog") else stat.S_IFREG | 0o644
            return _FakeSFTPAttr(mode)
        raise FileNotFoundError(path)

    mock_sftp.lstat.side_effect = _lstat

    connector, _ = _connect_ssh(mock_paramiko, mock_getaddrinfo, mock_socket_class, mock_sftp=mock_sftp)
    records = connector.list_urls(seed="/", limit=100)
    urls = {r.url for r in records}
    assert urls == {"/index.html", "/blog/post-1.html"}
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_list_urls_skips_tooling_directories(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    import stat

    mock_sftp = MagicMock()

    def _listdir_attr(remote_dir):
        if remote_dir == "/var/www/site":
            return [
                _FakeSFTPAttr(stat.S_IFDIR | 0o755, size=0, filename="node_modules"),
                _FakeSFTPAttr(stat.S_IFDIR | 0o755, size=0, filename=".git"),
                _FakeSFTPAttr(stat.S_IFREG | 0o644, size=10, filename="index.html"),
            ]
        raise AssertionError(f"不應該遞迴進入 tooling 目錄，卻嘗試列舉：{remote_dir}")

    mock_sftp.listdir_attr.side_effect = _listdir_attr

    def _lstat(path):
        if path == "/var/www/site/index.html":
            return _FakeSFTPAttr(stat.S_IFREG | 0o644)
        raise FileNotFoundError(path)

    mock_sftp.lstat.side_effect = _lstat

    connector, _ = _connect_ssh(mock_paramiko, mock_getaddrinfo, mock_socket_class, mock_sftp=mock_sftp)
    records = connector.list_urls(seed="/", limit=100)
    assert {r.url for r in records} == {"/index.html"}
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_list_urls_respects_limit(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    import stat

    mock_sftp = MagicMock()
    mock_sftp.listdir_attr.return_value = [
        _FakeSFTPAttr(stat.S_IFREG | 0o644, size=10, filename=f"page-{i}.html") for i in range(20)
    ]

    def _lstat(path):
        return _FakeSFTPAttr(stat.S_IFREG | 0o644)

    mock_sftp.lstat.side_effect = _lstat

    connector, _ = _connect_ssh(mock_paramiko, mock_getaddrinfo, mock_socket_class, mock_sftp=mock_sftp)
    records = connector.list_urls(seed="/", limit=5)
    assert len(records) == 5
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_fetch_url_rejects_query_string(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    connector, mock_sftp = _connect_ssh(mock_paramiko, mock_getaddrinfo, mock_socket_class)
    snapshot = connector.fetch_url("/index.html?ver=1.2")
    assert snapshot.fetch_error_type == "unsafe_remote_path"
    # 核心斷言：query string 應在任何 sftp 操作之前就被拒絕，不應該被
    # 靜默 strip 掉再嘗試讀取（那會讓行為看起來像成功但其實不是使用者
    # 以為的目標）。
    mock_sftp.lstat.assert_not_called()
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_fetch_url_rejects_fragment(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    connector, mock_sftp = _connect_ssh(mock_paramiko, mock_getaddrinfo, mock_socket_class)
    snapshot = connector.fetch_url("/index.html#section")
    assert snapshot.fetch_error_type == "unsafe_remote_path"
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_fetch_url_rejects_http_scheme(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    connector, mock_sftp = _connect_ssh(mock_paramiko, mock_getaddrinfo, mock_socket_class)
    snapshot = connector.fetch_url("http://169.254.169.254/evil")
    assert snapshot.fetch_error_type == "unsafe_remote_path"
    mock_sftp.lstat.assert_not_called()
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_fetch_url_accepts_plain_path(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    import stat

    mock_sftp = MagicMock()
    mock_sftp.lstat.return_value = _FakeSFTPAttr(stat.S_IFREG | 0o644, size=13)
    mock_file = MagicMock()
    mock_file.__enter__.return_value.read.return_value = b"<h1>Hi</h1>"
    mock_sftp.open.return_value = mock_file

    connector, _ = _connect_ssh(mock_paramiko, mock_getaddrinfo, mock_socket_class, mock_sftp=mock_sftp)
    snapshot = connector.fetch_url("/index.html")
    assert snapshot.status_code == 200
    assert "Hi" in snapshot.html
    connector.close()


# --- allowed_log_paths 驗證（建構子階段，不觸碰遠端） ---


def test_allowed_log_paths_rejects_invalid_log_type_key():
    from seo_advisor.security.ssh_log_safety import InvalidLogConfigError

    with pytest.raises(InvalidLogConfigError):
        SSHConnector(
            "example.com", user="deploy", remote_root="/var/www/site",
            confirm_connect="CONNECT example.com:22",
            allowed_log_paths={"Access-Log!": "/var/log/nginx/access.log"},
        )


def test_allowed_log_paths_rejects_relative_path():
    from seo_advisor.security.ssh_log_safety import InvalidLogConfigError

    with pytest.raises(InvalidLogConfigError):
        SSHConnector(
            "example.com", user="deploy", remote_root="/var/www/site",
            confirm_connect="CONNECT example.com:22",
            allowed_log_paths={"access": "var/log/nginx/access.log"},
        )


def test_allowed_log_paths_rejects_glob():
    from seo_advisor.security.ssh_log_safety import InvalidLogConfigError

    with pytest.raises(InvalidLogConfigError):
        SSHConnector(
            "example.com", user="deploy", remote_root="/var/www/site",
            confirm_connect="CONNECT example.com:22",
            allowed_log_paths={"access": "/var/log/nginx/*.log"},
        )


def test_allowed_log_paths_rejects_forbidden_root_as_entry():
    with pytest.raises(UnsafeRemotePathError):
        SSHConnector(
            "example.com", user="deploy", remote_root="/var/www/site",
            confirm_connect="CONNECT example.com:22",
            allowed_log_paths={"everything": "/var"},
        )


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_allowed_log_paths_accepts_var_log_path(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    """/var/log/nginx/access.log 這種常見 log 路徑必須放行——log jail 的
    過寬根檢查針對的是「條目本身等於過寬根目錄」，不是「任何位於 /var
    之下的路徑」（與網站 remote_root 的過寬檢查刻意不同語意）。"""
    connector, _ = _connect_ssh(
        mock_paramiko, mock_getaddrinfo, mock_socket_class,
        allowed_log_paths={"access": "/var/log/nginx/access.log"},
    )
    assert connector.capabilities() == {"read_files", "read_urls", "read_logs"}
    connector.close()


def _make_log_path_lstat(final_path: str, final_attr):
    """建立一個 lstat side_effect：final_path 之前的每一層中間目錄都回傳
    一個合法的目錄 stat（component-wise walk 需要逐層 lstat 成功才能繼續
    往下走），只有 final_path 本身回傳呼叫端指定的 final_attr。"""
    import stat

    components = final_path.strip("/").split("/")
    intermediate_paths = {
        "/" + "/".join(components[: i + 1]) for i in range(len(components) - 1)
    }

    def _lstat(path):
        if path == final_path:
            return final_attr
        if path in intermediate_paths:
            return _FakeSFTPAttr(stat.S_IFDIR | 0o755)
        raise FileNotFoundError(path)

    return _lstat


# --- get_logs()：tail 讀取、symlink 拒絕、since 不支援 ---


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_get_logs_returns_tail_lines(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    import stat

    mock_sftp = MagicMock()
    log_content = b"line-1\nline-2\nline-3\n"
    mock_sftp.lstat.side_effect = _make_log_path_lstat(
        "/var/log/nginx/access.log",
        _FakeSFTPAttr(stat.S_IFREG | 0o644, size=len(log_content)),
    )
    mock_file = MagicMock()
    mock_file.__enter__.return_value.read.return_value = log_content
    mock_sftp.open.return_value = mock_file

    connector, _ = _connect_ssh(
        mock_paramiko, mock_getaddrinfo, mock_socket_class, mock_sftp=mock_sftp,
        allowed_log_paths={"access": "/var/log/nginx/access.log"},
    )
    entries = connector.get_logs("access")
    messages = [e.message for e in entries]
    assert messages == ["line-1", "line-2", "line-3"]
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_get_logs_rejects_unknown_log_type(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    connector, _ = _connect_ssh(
        mock_paramiko, mock_getaddrinfo, mock_socket_class,
        allowed_log_paths={"access": "/var/log/nginx/access.log"},
    )
    with pytest.raises(SSHConnectorError):
        connector.get_logs("nonexistent-log-type")
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_get_logs_rejects_since_parameter(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    connector, _ = _connect_ssh(
        mock_paramiko, mock_getaddrinfo, mock_socket_class,
        allowed_log_paths={"access": "/var/log/nginx/access.log"},
    )
    with pytest.raises(SSHConnectorError, match="since"):
        connector.get_logs("access", since="1h")
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_get_logs_rejects_symlinked_log_file(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    """log 路徑最終節點若是 symlink，一律拒絕——與 read_file() 的
    component-wise walk 使用同一套規則，沒有「log 例外 follow」。"""
    import stat

    mock_sftp = MagicMock()
    mock_sftp.lstat.side_effect = _make_log_path_lstat(
        "/var/log/nginx/access.log", _FakeSFTPAttr(stat.S_IFLNK | 0o777, size=0)
    )

    connector, _ = _connect_ssh(
        mock_paramiko, mock_getaddrinfo, mock_socket_class, mock_sftp=mock_sftp,
        allowed_log_paths={"access": "/var/log/nginx/access.log"},
    )
    with pytest.raises(UnsafeRemotePathError):
        connector.get_logs("access")
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_get_logs_tail_reads_only_last_n_bytes(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    """驗證 tail 讀取邏輯：檔案很大時，只 seek 到尾端附近讀取，不會把
    整個檔案內容讀進記憶體（用超過 max_tail_bytes 上限的檔案大小驗證
    read() 呼叫的參數量級受 cap 限制，而非等於檔案總大小）。"""
    import stat

    huge_size = 50 * 1024 * 1024  # 50 MB，遠超過 256KB 預設 tail 上限
    mock_sftp = MagicMock()
    mock_sftp.lstat.side_effect = _make_log_path_lstat(
        "/var/log/nginx/access.log", _FakeSFTPAttr(stat.S_IFREG | 0o644, size=huge_size)
    )
    mock_file = MagicMock()
    mock_file.__enter__.return_value.read.return_value = b"partial-garbage\nline-a\nline-b\n"
    mock_sftp.open.return_value = mock_file

    connector, _ = _connect_ssh(
        mock_paramiko, mock_getaddrinfo, mock_socket_class, mock_sftp=mock_sftp,
        allowed_log_paths={"access": "/var/log/nginx/access.log"},
    )
    entries = connector.get_logs("access")
    # 讀取起點落在檔案中段，第一個不完整片段（"partial-garbage"）應被丟棄。
    messages = [e.message for e in entries]
    assert "partial-garbage" not in messages
    assert messages == ["line-a", "line-b"]

    # 驗證 seek 被呼叫到接近尾端的位置（不是從 0 開始讀）。
    seek_call_args = mock_file.__enter__.return_value.seek.call_args
    assert seek_call_args is not None
    seek_position = seek_call_args[0][0]
    assert seek_position > 0
    assert seek_position >= huge_size - (256 * 1024) - 1
    connector.close()


@patch("socket.socket")
@patch("socket.getaddrinfo")
@patch("seo_advisor.connectors.ssh.paramiko")
def test_get_logs_redacts_secrets_in_lines(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    import stat

    mock_sftp = MagicMock()
    log_line = b"GET /page?token=SUPERSECRET123 - password=hunter2\n"
    mock_sftp.lstat.side_effect = _make_log_path_lstat(
        "/var/log/nginx/access.log", _FakeSFTPAttr(stat.S_IFREG | 0o644, size=len(log_line))
    )
    mock_file = MagicMock()
    mock_file.__enter__.return_value.read.return_value = log_line
    mock_sftp.open.return_value = mock_file

    connector, _ = _connect_ssh(
        mock_paramiko, mock_getaddrinfo, mock_socket_class, mock_sftp=mock_sftp,
        allowed_log_paths={"access": "/var/log/nginx/access.log"},
    )
    entries = connector.get_logs("access")
    assert len(entries) == 1
    assert "hunter2" not in entries[0].message
    connector.close()


