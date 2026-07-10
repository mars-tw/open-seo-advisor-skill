"""security/ssh_log_safety.py 的單元測試：allowed_log_paths 語法驗證、
log path 的 component-wise walk 解析、tail 讀取邏輯。

不需要真實 SFTP 連線，用假的 sftp client mock 驗證核心邏輯。
"""

from __future__ import annotations

import stat
from unittest.mock import MagicMock

import pytest

from seo_advisor.security.ssh_log_safety import (
    InvalidLogConfigError,
    resolve_log_path,
    tail_log_content,
    validate_allowed_log_paths,
)
from seo_advisor.security.ssh_path_safety import RemotePathNotFoundError, UnsafeRemotePathError


class _FakeAttr:
    def __init__(self, mode, size=0):
        self.st_mode = mode
        self.st_size = size


def _dir_chain_lstat(final_path: str, final_attr):
    components = final_path.strip("/").split("/")
    intermediate = {"/" + "/".join(components[: i + 1]) for i in range(len(components) - 1)}

    def _lstat(path):
        if path == final_path:
            return final_attr
        if path in intermediate:
            return _FakeAttr(stat.S_IFDIR | 0o755)
        raise FileNotFoundError(path)

    return _lstat


class TestValidateAllowedLogPaths:
    def test_accepts_valid_config(self):
        result = validate_allowed_log_paths({"access": "/var/log/nginx/access.log"})
        assert result == {"access": "/var/log/nginx/access.log"}

    def test_rejects_uppercase_log_type(self):
        with pytest.raises(InvalidLogConfigError):
            validate_allowed_log_paths({"Access": "/var/log/nginx/access.log"})

    def test_rejects_special_chars_in_log_type(self):
        with pytest.raises(InvalidLogConfigError):
            validate_allowed_log_paths({"access!": "/var/log/nginx/access.log"})

    def test_accepts_underscore_and_dash_in_log_type(self):
        result = validate_allowed_log_paths({"nginx_access-log": "/var/log/nginx/access.log"})
        assert "nginx_access-log" in result

    def test_rejects_relative_path(self):
        with pytest.raises(InvalidLogConfigError):
            validate_allowed_log_paths({"access": "var/log/nginx/access.log"})

    def test_rejects_glob_asterisk(self):
        with pytest.raises(InvalidLogConfigError):
            validate_allowed_log_paths({"access": "/var/log/nginx/*.log"})

    def test_rejects_glob_question_mark(self):
        with pytest.raises(InvalidLogConfigError):
            validate_allowed_log_paths({"access": "/var/log/nginx/access?.log"})

    def test_rejects_glob_bracket(self):
        with pytest.raises(InvalidLogConfigError):
            validate_allowed_log_paths({"access": "/var/log/nginx/access[0-9].log"})

    def test_rejects_forbidden_root_as_entry(self):
        with pytest.raises(UnsafeRemotePathError):
            validate_allowed_log_paths({"everything": "/var"})

    def test_accepts_path_under_var_log(self):
        """/var/log/... 這種常見 log 路徑必須放行，過寬根檢查針對的是
        「條目本身等於過寬根目錄」，不是「任何位於 /var 之下的路徑」。"""
        result = validate_allowed_log_paths({"access": "/var/log/nginx/access.log"})
        assert result == {"access": "/var/log/nginx/access.log"}


class TestResolveLogPath:
    def test_resolves_valid_regular_file(self):
        sftp = MagicMock()
        sftp.lstat.side_effect = _dir_chain_lstat(
            "/var/log/nginx/access.log", _FakeAttr(stat.S_IFREG | 0o644, size=100)
        )
        resolved = resolve_log_path(sftp, "/var/log/nginx/access.log")
        assert resolved == "/var/log/nginx/access.log"

    def test_rejects_symlink_final_component(self):
        sftp = MagicMock()
        sftp.lstat.side_effect = _dir_chain_lstat(
            "/var/log/nginx/access.log", _FakeAttr(stat.S_IFLNK | 0o777)
        )
        with pytest.raises(UnsafeRemotePathError):
            resolve_log_path(sftp, "/var/log/nginx/access.log")

    def test_rejects_symlink_in_middle_of_path(self):
        """父目錄鏈上任一層是 symlink 也必須拒絕，不只是最終節點。"""
        sftp = MagicMock()

        def _lstat(path):
            if path == "/var/log/nginx":
                return _FakeAttr(stat.S_IFLNK | 0o777)
            if path in ("/var", "/var/log"):
                return _FakeAttr(stat.S_IFDIR | 0o755)
            raise FileNotFoundError(path)

        sftp.lstat.side_effect = _lstat
        with pytest.raises(UnsafeRemotePathError):
            resolve_log_path(sftp, "/var/log/nginx/access.log")

    def test_rejects_directory_as_log_path(self):
        sftp = MagicMock()
        sftp.lstat.side_effect = _dir_chain_lstat(
            "/var/log/nginx/access.log", _FakeAttr(stat.S_IFDIR | 0o755)
        )
        with pytest.raises(UnsafeRemotePathError):
            resolve_log_path(sftp, "/var/log/nginx/access.log")

    def test_raises_not_found_when_missing(self):
        sftp = MagicMock()
        sftp.lstat.side_effect = FileNotFoundError()
        with pytest.raises(RemotePathNotFoundError):
            resolve_log_path(sftp, "/var/log/nginx/access.log")


class TestTailLogContent:
    def test_reads_small_file_from_start(self):
        sftp = MagicMock()
        content = b"line-1\nline-2\n"
        sftp.lstat.return_value = _FakeAttr(stat.S_IFREG | 0o644, size=len(content))
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = content
        sftp.open.return_value = mock_file

        result = tail_log_content(sftp, "/var/log/nginx/access.log", max_tail_bytes=1024)
        assert result == content
        # 檔案小於上限時不需要 seek。
        mock_file.__enter__.return_value.seek.assert_not_called()

    def test_seeks_to_tail_for_large_file(self):
        sftp = MagicMock()
        huge_size = 10 * 1024 * 1024
        sftp.lstat.return_value = _FakeAttr(stat.S_IFREG | 0o644, size=huge_size)
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = b"partial\nclean-line\n"
        sftp.open.return_value = mock_file

        tail_log_content(sftp, "/var/log/nginx/access.log", max_tail_bytes=1024)

        seek_args = mock_file.__enter__.return_value.seek.call_args[0]
        assert seek_args[0] == huge_size - 1024

    def test_discards_first_partial_line_when_seeking(self):
        sftp = MagicMock()
        sftp.lstat.return_value = _FakeAttr(stat.S_IFREG | 0o644, size=10 * 1024 * 1024)
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = b"partial-garbage\nclean-1\nclean-2\n"
        sftp.open.return_value = mock_file

        result = tail_log_content(sftp, "/var/log/nginx/access.log", max_tail_bytes=1024)
        assert result == b"clean-1\nclean-2\n"

    def test_returns_empty_when_no_newline_found_in_window(self):
        sftp = MagicMock()
        sftp.lstat.return_value = _FakeAttr(stat.S_IFREG | 0o644, size=10 * 1024 * 1024)
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = b"no-newline-at-all"
        sftp.open.return_value = mock_file

        result = tail_log_content(sftp, "/var/log/nginx/access.log", max_tail_bytes=1024)
        assert result == b""

    def test_rejects_symlink_before_reading(self):
        sftp = MagicMock()
        sftp.lstat.return_value = _FakeAttr(stat.S_IFLNK | 0o777)
        with pytest.raises(UnsafeRemotePathError):
            tail_log_content(sftp, "/var/log/nginx/access.log", max_tail_bytes=1024)
        sftp.open.assert_not_called()

    def test_read_amount_bounded_by_cap_regardless_of_reported_size(self):
        """即使 sftp server 回報異常巨大的檔案大小，read() 的參數上限仍然
        固定為 max_tail_bytes + 1，不會被拿去一次性配置對應大小的 buffer。"""
        sftp = MagicMock()
        absurd_size = 500 * 1024 * 1024 * 1024  # 500 GB
        sftp.lstat.return_value = _FakeAttr(stat.S_IFREG | 0o644, size=absurd_size)
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = b"x" * 100 + b"\nafter\n"
        sftp.open.return_value = mock_file

        tail_log_content(sftp, "/var/log/nginx/access.log", max_tail_bytes=1024)

        read_args = mock_file.__enter__.return_value.read.call_args[0]
        assert read_args[0] == 1024 + 1
