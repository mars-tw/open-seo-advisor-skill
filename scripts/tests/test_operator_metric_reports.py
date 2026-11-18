"""Read the files delivered by the CLI for sparse and explicitly zero input."""

import json

import pytest
from typer.testing import CliRunner

from seo_advisor.cli import app
from seo_advisor.growth.models import AnalyticsMetricRow
from seo_advisor.growth.providers.mock import MockAnalyticsProvider


@pytest.mark.parametrize("revenue", [None, 0])
def test_report_separates_missing_revenue_from_measured_zero(tmp_path, monkeypatch, revenue):
    row = AnalyticsMetricRow(channel="B2B", sessions=80, conversions=8,
                             cost_minor_units=100000, revenue_minor_units=revenue)
    monkeypatch.setattr(MockAnalyticsProvider, "fetch_metrics", lambda *args: [row])
    result = CliRunner().invoke(app, ["growth", "analytics", "--provider", "mock", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    report = json.loads((tmp_path / "analytics-report.json").read_bytes())
    assert report["rows"][0]["revenue_minor_units"] == revenue
    spends = [finding for finding in report["findings"] if finding["category"] == "spend"]
    if revenue is None:
        assert not spends and "尚無資料" in report["summary"]
    else:
        assert len(spends) == 1 and spends[0]["evidence"]["roas"] == 0


def test_name_only_listing_does_not_invent_stock_reviews_or_images(tmp_path):
    supplied = tmp_path / "m8.json"
    supplied.write_text('{"title":"M8 不鏽鋼螺絲"}', encoding="utf-8")
    result = CliRunner().invoke(app, ["ecommerce", "audit", "--input", str(supplied), "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    report = json.loads((tmp_path / "ecommerce-report.json").read_bytes())
    assert {item["category"] for item in report["findings"]} == {"title"}
    assert len(report["applied_checklist"]) == 2
    assert "2/10" in (tmp_path / "ecommerce-report.md").read_text(encoding="utf-8")
