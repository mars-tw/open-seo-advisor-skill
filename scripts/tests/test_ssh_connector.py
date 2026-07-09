"""SSHConnector 測試：連線前的安全閘門（網段檢查、確認字串）、讀取白名單/
denylist、capabilities() 誠實回報。真實 SSH/SFTP 連線用 mock 模擬，不依賴
真實伺服器；連線前的 DNS 解析/socket 建立也一併 mock，避免測試碰觸真實
網路（見 _resolve_and_verify_host 的 DNS TOCTOU 修法：只解析一次 DNS，
用解析出的 IP 直接建立 socket 再交給 paramiko）。"""

from unittest.mock import MagicMock, patch

import pytest

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
def test_capabilities_only_reports_read_files(mock_paramiko, mock_getaddrinfo, mock_socket_class):
    mock_client, mock_sftp = _make_mock_client()
    mock_paramiko.SSHClient.return_value = mock_client
    mock_paramiko.ssh_exception.SSHException = Exception
    _patch_dns_resolves_to_public_ip(mock_getaddrinfo, mock_socket_class)

    connector = SSHConnector(
        "example.com", user="deploy", remote_root="/var/www/site",
        confirm_connect="CONNECT example.com:22",
    )
    assert connector.capabilities() == {"read_files"}
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
    with pytest.raises(NotImplementedError):
        connector.get_logs("access", "1h")
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
