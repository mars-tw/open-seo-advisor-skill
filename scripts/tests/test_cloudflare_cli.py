"""`seo-advisor cloudflare audit` CLI 測試。"""

from __future__ import annotations

import httpx
import respx
from typer.testing import CliRunner

from seo_advisor.cli import app

runner = CliRunner()
_ZONE_ID = "0123456789abcdef0123456789abcdef"
_API = "https://api.cloudflare.com/client/v4"


def test_missing_token_env_var_fails_with_clear_message(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    result = runner.invoke(app, ["cloudflare", "audit", "--zone-id", _ZONE_ID])
    assert result.exit_code == 1
    assert "CLOUDFLARE_API_TOKEN" in result.stdout


def test_invalid_zone_id_format_rejected(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-token")
    result = runner.invoke(app, ["cloudflare", "audit", "--zone-id", "not-valid"])
    assert result.exit_code == 1


@respx.mock
def test_successful_audit_writes_reports(monkeypatch, tmp_path):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-token")

    respx.get(f"{_API}/user/tokens/verify").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"status": "active"}})
    )
    respx.get(f"{_API}/zones/{_ZONE_ID}").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"id": _ZONE_ID, "name": "example.com"}})
    )
    respx.get(f"{_API}/zones/{_ZONE_ID}/dns_records").mock(
        return_value=httpx.Response(
            200, json={"success": True, "result": [{"type": "A", "name": "example.com", "content": "1.2.3.4"}]}
        )
    )
    respx.get(f"{_API}/zones/{_ZONE_ID}/rulesets/phases/http_request_dynamic_redirect/entrypoint").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"id": "rs1", "rules": []}})
    )
    respx.get(f"{_API}/zones/{_ZONE_ID}/rulesets/phases/http_request_cache_settings/entrypoint").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"id": "rs2", "rules": []}})
    )
    respx.get(f"{_API}/zones/{_ZONE_ID}/pagerules").mock(
        return_value=httpx.Response(200, json={"success": True, "result": []})
    )

    out_dir = tmp_path / "cf-out"
    result = runner.invoke(
        app, ["cloudflare", "audit", "--zone-id", _ZONE_ID, "--out", str(out_dir)]
    )

    assert result.exit_code == 0
    assert (out_dir / "cloudflare-report.json").exists()
    assert (out_dir / "cloudflare-report.md").exists()
    assert "example.com" in (out_dir / "cloudflare-report.md").read_text(encoding="utf-8")


@respx.mock
def test_zone_name_mismatch_rejected(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-token")
    respx.get(f"{_API}/user/tokens/verify").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"status": "active"}})
    )
    respx.get(f"{_API}/zones/{_ZONE_ID}").mock(
        return_value=httpx.Response(
            200, json={"success": True, "result": {"id": _ZONE_ID, "name": "actual-domain.com"}}
        )
    )

    result = runner.invoke(
        app, ["cloudflare", "audit", "--zone-id", _ZONE_ID, "--zone-name", "wrong-domain.com"]
    )
    assert result.exit_code == 1
