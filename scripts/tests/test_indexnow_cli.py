"""`seo-advisor indexnow ...` 的 CLI 整合測試。"""

from __future__ import annotations

import httpx
import respx
from typer.testing import CliRunner

from seo_advisor.cli import app
from seo_advisor.indexnow.key import validate_key_format

runner = CliRunner()

_KEY = "abc12345key"
_KEY_LOCATION = "https://example.com/abc12345key.txt"


def _write_urls_file(tmp_path, urls: list[str]) -> str:
    path = tmp_path / "urls.txt"
    path.write_text("\n".join(urls), encoding="utf-8")
    return str(path)


class TestKeyGenerate:
    def test_prints_valid_key(self):
        result = runner.invoke(app, ["indexnow", "key", "generate"])
        assert result.exit_code == 0
        validate_key_format(result.stdout.strip())

    def test_writes_key_to_file(self, tmp_path):
        out = tmp_path / "key.txt"
        result = runner.invoke(app, ["indexnow", "key", "generate", "--out", str(out)])
        assert result.exit_code == 0
        validate_key_format(out.read_text(encoding="utf-8").strip())


class TestKeyCheck:
    def test_accepts_valid_key(self):
        result = runner.invoke(app, ["indexnow", "key", "check", "abc12345"])
        assert result.exit_code == 0

    def test_rejects_invalid_key(self):
        result = runner.invoke(app, ["indexnow", "key", "check", "short"])
        assert result.exit_code == 1


class TestSubmitDryRun:
    def test_dry_run_reports_accepted_and_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INDEXNOW_TEST_KEY", _KEY)
        urls_file = _write_urls_file(
            tmp_path, ["https://example.com/post-1", "https://evil.com/post-2"]
        )
        result = runner.invoke(
            app,
            [
                "indexnow", "submit",
                "--site", "https://example.com",
                "--urls-file", urls_file,
                "--key-env", "INDEXNOW_TEST_KEY",
                "--key-location", _KEY_LOCATION,
                "--out", str(tmp_path / "report"),
            ],
        )
        assert result.exit_code == 0
        assert "dry-run" in result.stdout
        assert "通過 scope 驗證：1 筆" in result.stdout
        assert "被拒絕：1 筆" in result.stdout
        assert (tmp_path / "report" / "indexnow-report.md").exists()
        assert (tmp_path / "report" / "indexnow-report.json").exists()

    def test_dry_run_does_not_make_network_request(self, tmp_path, monkeypatch):
        """dry-run 模式下即使沒有 mock 任何網路請求也不該報錯，因為根本
        不該發送任何請求（respx 預設會擋下未被 mock 的請求並拋錯）。"""
        monkeypatch.setenv("INDEXNOW_TEST_KEY", _KEY)
        urls_file = _write_urls_file(tmp_path, ["https://example.com/post-1"])
        with respx.mock:
            result = runner.invoke(
                app,
                [
                    "indexnow", "submit",
                    "--site", "https://example.com",
                    "--urls-file", urls_file,
                    "--key-env", "INDEXNOW_TEST_KEY",
                    "--key-location", _KEY_LOCATION,
                    "--out", str(tmp_path / "report"),
                ],
            )
        assert result.exit_code == 0

    def test_missing_urls_fails_with_clear_message(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INDEXNOW_TEST_KEY", _KEY)
        result = runner.invoke(
            app,
            [
                "indexnow", "submit",
                "--site", "https://example.com",
                "--key-env", "INDEXNOW_TEST_KEY",
                "--key-location", _KEY_LOCATION,
                "--out", str(tmp_path / "report"),
            ],
        )
        assert result.exit_code == 1
        assert "URL" in result.stdout

    def test_missing_key_fails_with_clear_message(self, tmp_path):
        urls_file = _write_urls_file(tmp_path, ["https://example.com/post-1"])
        result = runner.invoke(
            app,
            [
                "indexnow", "submit",
                "--site", "https://example.com",
                "--urls-file", urls_file,
                "--key-location", _KEY_LOCATION,
                "--out", str(tmp_path / "report"),
            ],
        )
        assert result.exit_code == 1
        assert "key" in result.stdout


class TestSubmitSend:
    def test_send_without_confirm_is_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INDEXNOW_TEST_KEY", _KEY)
        urls_file = _write_urls_file(tmp_path, ["https://example.com/post-1"])
        result = runner.invoke(
            app,
            [
                "indexnow", "submit",
                "--site", "https://example.com",
                "--urls-file", urls_file,
                "--key-env", "INDEXNOW_TEST_KEY",
                "--key-location", _KEY_LOCATION,
                "--send",
                "--out", str(tmp_path / "report"),
            ],
        )
        assert result.exit_code == 1
        assert "確認字串" in result.stdout

    def test_send_with_wrong_confirm_is_rejected(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INDEXNOW_TEST_KEY", _KEY)
        urls_file = _write_urls_file(tmp_path, ["https://example.com/post-1"])
        result = runner.invoke(
            app,
            [
                "indexnow", "submit",
                "--site", "https://example.com",
                "--urls-file", urls_file,
                "--key-env", "INDEXNOW_TEST_KEY",
                "--key-location", _KEY_LOCATION,
                "--send",
                "--confirm", "SUBMIT INDEXNOW example.com 999",
                "--out", str(tmp_path / "report"),
            ],
        )
        assert result.exit_code == 1

    @respx.mock
    def test_send_with_correct_confirm_submits(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INDEXNOW_TEST_KEY", _KEY)
        urls_file = _write_urls_file(tmp_path, ["https://example.com/post-1"])
        respx.get(_KEY_LOCATION).mock(return_value=httpx.Response(200, text=_KEY))
        respx.post("https://api.indexnow.org/indexnow").mock(return_value=httpx.Response(200))

        result = runner.invoke(
            app,
            [
                "indexnow", "submit",
                "--site", "https://example.com",
                "--urls-file", urls_file,
                "--key-env", "INDEXNOW_TEST_KEY",
                "--key-location", _KEY_LOCATION,
                "--send",
                "--confirm", "SUBMIT INDEXNOW example.com 1",
                "--out", str(tmp_path / "report"),
            ],
        )
        assert result.exit_code == 0
        assert "已送出提交" in result.stdout
        assert "送出：1 筆" in result.stdout

    @respx.mock
    def test_send_confirm_is_case_insensitive(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INDEXNOW_TEST_KEY", _KEY)
        urls_file = _write_urls_file(tmp_path, ["https://example.com/post-1"])
        respx.get(_KEY_LOCATION).mock(return_value=httpx.Response(200, text=_KEY))
        respx.post("https://api.indexnow.org/indexnow").mock(return_value=httpx.Response(200))

        result = runner.invoke(
            app,
            [
                "indexnow", "submit",
                "--site", "https://example.com",
                "--urls-file", urls_file,
                "--key-env", "INDEXNOW_TEST_KEY",
                "--key-location", _KEY_LOCATION,
                "--send",
                "--confirm", "submit indexnow example.com 1",
                "--out", str(tmp_path / "report"),
            ],
        )
        assert result.exit_code == 0

    def test_send_rejects_private_network_key_location_by_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INDEXNOW_TEST_KEY", _KEY)
        urls_file = _write_urls_file(tmp_path, ["http://127.0.0.1/post-1"])
        result = runner.invoke(
            app,
            [
                "indexnow", "submit",
                "--site", "http://127.0.0.1",
                "--urls-file", urls_file,
                "--key-env", "INDEXNOW_TEST_KEY",
                "--key-location", "http://127.0.0.1/abc12345key.txt",
                "--send",
                "--confirm", "SUBMIT INDEXNOW 127.0.0.1 1",
                "--out", str(tmp_path / "report"),
            ],
        )
        assert result.exit_code == 1

    @respx.mock
    def test_send_stops_when_key_verification_fails(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INDEXNOW_TEST_KEY", _KEY)
        urls_file = _write_urls_file(tmp_path, ["https://example.com/post-1"])
        respx.get(_KEY_LOCATION).mock(return_value=httpx.Response(404))

        result = runner.invoke(
            app,
            [
                "indexnow", "submit",
                "--site", "https://example.com",
                "--urls-file", urls_file,
                "--key-env", "INDEXNOW_TEST_KEY",
                "--key-location", _KEY_LOCATION,
                "--send",
                "--confirm", "SUBMIT INDEXNOW example.com 1",
                "--out", str(tmp_path / "report"),
            ],
        )
        assert result.exit_code == 1


class TestSubmitMaxUrls:
    def test_max_urls_truncates_and_notes_it(self, tmp_path, monkeypatch):
        monkeypatch.setenv("INDEXNOW_TEST_KEY", _KEY)
        urls_file = _write_urls_file(
            tmp_path, [f"https://example.com/post-{i}" for i in range(5)]
        )
        result = runner.invoke(
            app,
            [
                "indexnow", "submit",
                "--site", "https://example.com",
                "--urls-file", urls_file,
                "--key-env", "INDEXNOW_TEST_KEY",
                "--key-location", _KEY_LOCATION,
                "--max-urls", "2",
                "--out", str(tmp_path / "report"),
            ],
        )
        assert result.exit_code == 0
        assert "超過 --max-urls 上限" in result.stdout
