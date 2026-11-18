"""Run the public CLI examples that previously advertised unavailable features."""

import json
import shlex
from pathlib import Path

import httpx
import pytest
import respx
from markdown_it import MarkdownIt
from typer.testing import CliRunner

from seo_advisor.cli import app
from seo_advisor.growth.providers.base import AnalyticsProviderError
from seo_advisor.growth.providers.factory import create_analytics_provider


ROOT = Path(__file__).resolve().parents[2]


def documented_commands(filename, prefix):
    doc = (ROOT / filename).read_text(encoding="utf-8")
    commands = []
    for block in MarkdownIt().enable("table").parse(doc):
        snippets = [child.content for child in block.children or [] if child.type == "code_inline"]
        if block.type == "fence" and block.info == "bash":
            snippets.extend(block.content.splitlines())
        commands.extend(shlex.split(line, comments=True)[1:] for line in snippets if line.startswith(prefix))
    assert commands, f"No example for {prefix} in {filename}"
    return commands


@respx.mock
def test_documented_market_audit_and_plugin_commands(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    host = "https://example.com"
    respx.get(host + "/robots.txt").mock(return_value=httpx.Response(404))
    respx.get(host + "/sitemap.xml").mock(return_value=httpx.Response(404))
    respx.get(host + "/").mock(return_value=httpx.Response(
        200, headers={"content-type": "text/html"}, text="<html><title>Example</title></html>"))
    runner = CliRunner()
    for filename, prefix in [
        ("docs/i18n_seo_guide.md", "seo-advisor audit consultant "),
        ("docs/capability-map.md", "seo-advisor plugin dev "),
        ("docs/growth_marketing.md", "seo-advisor growth analytics "),
    ]:
        for args in documented_commands(filename, prefix):
            result = runner.invoke(app, args)
            assert result.exit_code == 0, (args, result.output)
    assert (tmp_path / "report/report.json").is_file()
    assert list((tmp_path / "plugin-dev").glob("*.zip"))
    output = (tmp_path / "growth-analytics/analytics-report.json").read_text(encoding="utf-8")
    assert json.loads(output)["source"] == "mock"


@pytest.mark.parametrize(("name", "setting"), [
    ("ga4", "GA4_PROPERTY_ID"), ("search_console", "GSC_SITE_URL"),
    ("google_ads", "GOOGLE_ADS_DEVELOPER_TOKEN"),
])
def test_reserved_google_providers_do_not_promise_live_data(name, setting, monkeypatch):
    monkeypatch.setenv(setting, "test-only")
    with pytest.raises(AnalyticsProviderError, match="尚未.*實作"):
        create_analytics_provider(name).fetch_metrics("test-only", 28)
    monkeypatch.delenv(setting)
    result = CliRunner().invoke(app, ["growth", "analytics", "--provider", name])
    assert result.exit_code == 1
    assert "尚未實作" in result.output
    assert "設定好之後" not in result.output
