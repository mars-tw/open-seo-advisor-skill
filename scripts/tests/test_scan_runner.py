from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from seo_advisor.scan_runner import SSHSourceOptions, SiteUnreachableError, run_consultant_scan


@respx.mock
def test_unreachable_site_raises_friendly_error(tmp_path):
    respx.get("https://totally-unreachable-example.test/").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    respx.get("https://totally-unreachable-example.test/robots.txt").mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    respx.get("https://totally-unreachable-example.test/sitemap.xml").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    with pytest.raises(SiteUnreachableError):
        run_consultant_scan(
            url="https://totally-unreachable-example.test",
            source=None,
            out_dir=str(tmp_path / "report"),
        )


@respx.mock
def test_site_with_404_homepage_still_produces_report(tmp_path):
    # 網站有回應（即使是 404），代表連線層級沒問題，應該正常產出報告
    # 而不是被 preflight 擋下。
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/").mock(return_value=httpx.Response(404, text="Not Found"))

    outcome = run_consultant_scan(
        url="https://example.com", source=None, out_dir=str(tmp_path / "report")
    )

    assert outcome.report is not None
    assert outcome.beginner_path.exists()


@respx.mock
def test_reachable_site_scans_normally(tmp_path):
    respx.get("https://example.com/robots.txt").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get("https://example.com/").mock(
        return_value=httpx.Response(200, text="<html><title>Home</title></html>")
    )

    outcome = run_consultant_scan(
        url="https://example.com", source=None, out_dir=str(tmp_path / "report")
    )

    assert outcome.report.site_health_score >= 0
    assert outcome.technical_path.exists()
    assert outcome.json_path.exists()


# --- 三選一互斥邏輯 ---


def test_neither_url_nor_source_raises(tmp_path):
    with pytest.raises(ValueError, match="必須提供"):
        run_consultant_scan(url=None, source=None, out_dir=str(tmp_path / "report"))


def test_url_and_source_together_raises(tmp_path):
    with pytest.raises(ValueError, match="必須提供"):
        run_consultant_scan(
            url="https://example.com", source="./local", out_dir=str(tmp_path / "report")
        )


def test_source_ssh_without_ssh_options_raises(tmp_path):
    with pytest.raises(ValueError, match="ssh_options"):
        run_consultant_scan(url=None, source="ssh", out_dir=str(tmp_path / "report"))


def test_url_and_ssh_options_together_raises(tmp_path):
    ssh_options = SSHSourceOptions(
        host="example.com", user="deploy", remote_root="/var/www/site",
        confirm_connect="CONNECT example.com:22",
    )
    with pytest.raises(ValueError, match="source"):
        run_consultant_scan(
            url="https://example.com", source=None, out_dir=str(tmp_path / "report"),
            ssh_options=ssh_options,
        )


# --- source="ssh" 走 SSHConnector（mock 連線層，不碰真實網路）---


@patch("seo_advisor.scan_runner.SSHConnector")
def test_ssh_source_builds_connector_with_ssh_options(mock_ssh_connector_class, tmp_path):
    from seo_advisor.models import ConnectorProfile, PageSnapshot, UrlRecord

    mock_connector = MagicMock()
    mock_connector.probe.return_value = ConnectorProfile(
        source_type="ssh", detected_stack=None, notes=["已連線"]
    )
    mock_connector.list_urls.return_value = [
        UrlRecord(url="/index.html", source="crawl", discovered_depth=0)
    ]
    mock_connector.fetch_url.return_value = PageSnapshot(
        url="/index.html", status_code=200, final_url="/index.html",
        html="<html><title>Home</title></html>", fetched_at="",
    )
    mock_ssh_connector_class.return_value = mock_connector

    ssh_options = SSHSourceOptions(
        host="example.com", user="deploy", remote_root="/var/www/site",
        confirm_connect="CONNECT example.com:22",
    )
    outcome = run_consultant_scan(
        url=None, source="ssh", out_dir=str(tmp_path / "report"), ssh_options=ssh_options
    )

    assert outcome.report is not None
    mock_ssh_connector_class.assert_called_once()
    call_kwargs = mock_ssh_connector_class.call_args.kwargs
    assert call_kwargs["user"] == "deploy"
    assert call_kwargs["remote_root"] == "/var/www/site"
    assert call_kwargs["confirm_connect"] == "CONNECT example.com:22"
