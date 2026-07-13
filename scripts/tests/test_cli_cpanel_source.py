"""`seo-advisor audit consultant --source cpanel` 的 CLI 參數驗證測試。

只測試 CLI 層的參數收集/驗證邏輯，不觸碰真實 cPanel 連線——實際掃描邏輯
已由 test_cpanel_connector.py 覆蓋。
"""

from __future__ import annotations

from typer.testing import CliRunner

from seo_advisor.cli import app

runner = CliRunner()


def test_source_cpanel_without_any_flags_fails_with_clear_message():
    result = runner.invoke(app, ["audit", "consultant", "--source", "cpanel"])
    assert result.exit_code == 1
    assert "--cpanel-host" in result.stdout
    assert "--cpanel-user" in result.stdout
    assert "--cpanel-confirm" in result.stdout


def test_source_cpanel_missing_only_confirm_reports_that_one():
    result = runner.invoke(
        app,
        [
            "audit", "consultant",
            "--source", "cpanel",
            "--cpanel-host", "example.com",
            "--cpanel-user", "myuser",
        ],
    )
    assert result.exit_code == 1
    assert "--cpanel-confirm" in result.stdout


def test_url_and_source_cpanel_together_rejected():
    result = runner.invoke(
        app,
        [
            "audit", "consultant",
            "--url", "example.com",
            "--source", "cpanel",
            "--cpanel-host", "example.com",
            "--cpanel-user", "myuser",
            "--cpanel-confirm", "CONNECT CPANEL example.com:2083",
        ],
    )
    assert result.exit_code == 1
    assert "不可同時提供" in result.stdout
