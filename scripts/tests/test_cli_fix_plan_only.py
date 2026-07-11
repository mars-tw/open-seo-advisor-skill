"""`seo-advisor fix engineer` 對 plan_only 修復類型（redirect/hreflang/
blocking script 建議）的 CLI 顯示行為測試：不應提示 --apply --confirm，
且輸出的 fix-plan.json 應保留 plan_only=True。
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from seo_advisor.cli import app

runner = CliRunner()


def _write_report(tmp_path, findings: list[dict]) -> str:
    report = {
        "report_id": "r1",
        "generated_at": "2026-01-01T00:00:00Z",
        "target": {"source_type": "local_archive", "identifier": "x"},
        "mode": "consultant",
        "executive_summary": "test",
        "site_health_score": 80,
        "findings": findings,
        "top_findings": [],
        "coverage_notes": [],
        "scan_stats": {},
    }
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    return str(report_path)


def _redirect_chain_finding() -> dict:
    return {
        "id": "SEO-REDIRECT_CHAIN-001",
        "title": "test redirect chain",
        "mode": "consultant",
        "category": "indexability",
        "severity": "P2",
        "impact": 3,
        "effort": 1,
        "confidence": 0.9,
        "affected_urls": ["https://example.com/old"],
        "evidence": {
            "example_chain": [
                "https://example.com/old",
                "https://example.com/mid",
                "https://example.com/new",
            ]
        },
        "recommendation": "test",
        "validation": [],
        "owner": "engineer",
    }


def test_plan_only_output_has_no_apply_prompt(tmp_path):
    (tmp_path / "site").mkdir()
    report_path = _write_report(tmp_path, [_redirect_chain_finding()])

    result = runner.invoke(
        app,
        [
            "fix", "engineer",
            "--source", str(tmp_path / "site"),
            "--from-report", report_path,
            "--finding-id", "SEO-REDIRECT_CHAIN-001",
            "--out", str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 0
    assert "建議" in result.stdout
    # 不應出現可複製貼上執行的 apply 指令範例（那個提示只在真正可套用的
    # 計畫才會出現，plan_only 計畫沒有這種指令可執行）。
    assert "seo-advisor fix engineer" not in result.stdout
    assert "--confirm \"" not in result.stdout


def test_plan_only_json_output_preserves_flag(tmp_path):
    (tmp_path / "site").mkdir()
    report_path = _write_report(tmp_path, [_redirect_chain_finding()])

    runner.invoke(
        app,
        [
            "fix", "engineer",
            "--source", str(tmp_path / "site"),
            "--from-report", report_path,
            "--finding-id", "SEO-REDIRECT_CHAIN-001",
            "--out", str(tmp_path / "out"),
        ],
    )

    plan_json = json.loads((tmp_path / "out" / "fix-plan.json").read_text(encoding="utf-8"))
    assert plan_json["plan_only"] is True
    assert plan_json["targets"] == []
    assert len(plan_json["suggested_actions"]) > 0


def test_plan_only_markdown_shows_suggested_actions_not_diff(tmp_path):
    (tmp_path / "site").mkdir()
    report_path = _write_report(tmp_path, [_redirect_chain_finding()])

    runner.invoke(
        app,
        [
            "fix", "engineer",
            "--source", str(tmp_path / "site"),
            "--from-report", report_path,
            "--finding-id", "SEO-REDIRECT_CHAIN-001",
            "--out", str(tmp_path / "out"),
        ],
    )

    markdown = (tmp_path / "out" / "fix-plan.md").read_text(encoding="utf-8")
    assert "建議步驟" in markdown
    assert "變更內容" not in markdown
