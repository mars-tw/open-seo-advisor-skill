"""`seo-advisor audit consultant --source ssh` 的 CLI 參數驗證測試。

只測試 CLI 層的參數收集/驗證邏輯（缺少必要 --ssh-* 參數時的錯誤處理、
--url 與 --source 互斥檢查），不觸碰真實 SSH 連線——實際掃描邏輯已由
test_ssh_connector.py 與 scan_runner 的呼叫路徑覆蓋。
"""

from __future__ import annotations

from typer.testing import CliRunner

from seo_advisor.cli import app

runner = CliRunner()


def test_source_ssh_without_any_ssh_flags_fails_with_clear_message():
    result = runner.invoke(app, ["audit", "consultant", "--source", "ssh"])
    assert result.exit_code == 1
    assert "--ssh-host" in result.stdout
    assert "--ssh-user" in result.stdout
    assert "--ssh-remote-root" in result.stdout
    assert "--ssh-confirm" in result.stdout


def test_source_ssh_missing_only_confirm_reports_that_one():
    result = runner.invoke(
        app,
        [
            "audit", "consultant",
            "--source", "ssh",
            "--ssh-host", "example.com",
            "--ssh-user", "deploy",
            "--ssh-remote-root", "/var/www/site",
        ],
    )
    assert result.exit_code == 1
    assert "--ssh-confirm" in result.stdout
    assert "--ssh-host" not in result.stdout.split("錯誤")[-1]


def test_url_and_source_ssh_together_rejected():
    result = runner.invoke(
        app,
        [
            "audit", "consultant",
            "--url", "example.com",
            "--source", "ssh",
            "--ssh-host", "example.com",
            "--ssh-user", "deploy",
            "--ssh-remote-root", "/var/www/site",
            "--ssh-confirm", "CONNECT example.com:22",
        ],
    )
    assert result.exit_code == 1
    assert "不可同時提供" in result.stdout


def test_neither_url_nor_source_rejected():
    result = runner.invoke(app, ["audit", "consultant"])
    assert result.exit_code == 1
    assert "必須提供" in result.stdout
