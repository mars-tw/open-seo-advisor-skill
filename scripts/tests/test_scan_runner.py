import httpx
import pytest
import respx

from seo_advisor.scan_runner import SiteUnreachableError, run_consultant_scan


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
