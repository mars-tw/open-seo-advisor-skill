import httpx
import pytest
import respx

from seo_advisor.connectors.base import ConnectorCapabilityError
from seo_advisor.connectors.cloudflare import (
    CloudflareAuthError,
    CloudflareConflictError,
    CloudflareConnector,
    CloudflareConnectorError,
    CloudflareZoneNotFoundError,
)
from seo_advisor.models import SafetyPolicy
from seo_advisor.security.cloudflare_safety import InvalidZoneIdError

_ZONE_ID = "0123456789abcdef0123456789abcdef"
_API = "https://api.cloudflare.com/client/v4"


def _mock_token_verify_ok():
    respx.get(f"{_API}/user/tokens/verify").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"status": "active"}})
    )


def _mock_zone_ok(zone_name: str = "example.com"):
    respx.get(f"{_API}/zones/{_ZONE_ID}").mock(
        return_value=httpx.Response(
            200, json={"success": True, "result": {"id": _ZONE_ID, "name": zone_name}}
        )
    )


def _make_connector(**kwargs) -> CloudflareConnector:
    _mock_token_verify_ok()
    _mock_zone_ok()
    return CloudflareConnector(_ZONE_ID, api_token="test-token", **kwargs)


class TestConstructorValidation:
    def test_rejects_invalid_zone_id_format(self):
        with pytest.raises(InvalidZoneIdError):
            CloudflareConnector("not-a-valid-zone-id", api_token="test-token")

    def test_rejects_missing_token(self, monkeypatch):
        monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
        with pytest.raises(CloudflareConnectorError, match="Token"):
            CloudflareConnector(_ZONE_ID, api_token=None)

    @respx.mock
    def test_rejects_invalid_token(self):
        respx.get(f"{_API}/user/tokens/verify").mock(
            return_value=httpx.Response(401, json={"success": False, "errors": []})
        )
        with pytest.raises(CloudflareAuthError):
            CloudflareConnector(_ZONE_ID, api_token="bad-token")

    @respx.mock
    def test_rejects_zone_not_found(self):
        _mock_token_verify_ok()
        respx.get(f"{_API}/zones/{_ZONE_ID}").mock(
            return_value=httpx.Response(404, json={"success": False, "errors": []})
        )
        with pytest.raises(CloudflareZoneNotFoundError):
            CloudflareConnector(_ZONE_ID, api_token="test-token")

    @respx.mock
    def test_rejects_zone_name_mismatch(self):
        _mock_token_verify_ok()
        _mock_zone_ok(zone_name="actual-domain.com")
        with pytest.raises(CloudflareConnectorError, match="不一致"):
            CloudflareConnector(_ZONE_ID, api_token="test-token", zone_name="wrong-domain.com")

    @respx.mock
    def test_accepts_matching_zone_name(self):
        connector = _make_connector(zone_name="example.com")
        assert connector.id() == "cloudflare:example.com"
        connector.close()


class TestCapabilities:
    @respx.mock
    def test_capabilities_read_only_by_default(self):
        connector = _make_connector()
        assert connector.capabilities() == {"read_cloudflare_config"}
        connector.close()

    @respx.mock
    def test_capabilities_include_deploy_when_policy_allows(self):
        policy = SafetyPolicy(allowed_capabilities={"read_cloudflare_config", "deploy_cloudflare_rules"})
        connector = _make_connector(policy=policy)
        assert connector.capabilities() == {"read_cloudflare_config", "deploy_cloudflare_rules"}
        connector.close()

    @respx.mock
    def test_list_urls_not_supported(self):
        connector = _make_connector()
        with pytest.raises(ConnectorCapabilityError):
            connector.list_urls(seed="/", limit=10)
        connector.close()

    @respx.mock
    def test_fetch_url_not_supported(self):
        connector = _make_connector()
        with pytest.raises(ConnectorCapabilityError):
            connector.fetch_url("https://example.com/")
        connector.close()


class TestReadOnlySnapshot:
    @respx.mock
    def test_build_snapshot_collects_all_sections(self):
        _mock_token_verify_ok()
        _mock_zone_ok()
        respx.get(f"{_API}/zones/{_ZONE_ID}/dns_records").mock(
            return_value=httpx.Response(
                200,
                json={"success": True, "result": [{"type": "A", "name": "example.com", "content": "1.2.3.4"}]},
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

        connector = CloudflareConnector(_ZONE_ID, api_token="test-token")
        snapshot = connector.build_snapshot()

        assert snapshot["zone_name"] == "example.com"
        assert len(snapshot["dns_records"]) == 1
        assert snapshot["redirect_rules"] == []
        connector.close()

    @respx.mock
    def test_permission_denied_on_dns_records_does_not_crash_snapshot(self):
        _mock_token_verify_ok()
        _mock_zone_ok()
        respx.get(f"{_API}/zones/{_ZONE_ID}/dns_records").mock(
            return_value=httpx.Response(403, json={"success": False, "errors": []})
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

        connector = CloudflareConnector(_ZONE_ID, api_token="test-token")
        snapshot = connector.build_snapshot()

        assert snapshot["dns_records"] == []
        assert any("權限" in note for note in snapshot["permission_notes"])
        connector.close()

    @respx.mock
    def test_list_dns_records_requires_capability(self):
        policy = SafetyPolicy(allowed_capabilities=set())
        connector = _make_connector(policy=policy)
        with pytest.raises(PermissionError):
            connector.list_dns_records()
        connector.close()


class TestDeployPatchRedirectRule:
    @respx.mock
    def test_dry_run_does_not_send_write_request(self):
        policy = SafetyPolicy(
            dry_run=True, allowed_capabilities={"read_cloudflare_config", "deploy_cloudflare_rules"}
        )
        connector = _make_connector(policy=policy)

        result = connector.deploy_patch(
            {
                "patch_id": "p1",
                "source_path": "/old-page",
                "target_url": "https://example.com/new-page",
                "status_code": 301,
                "base_ruleset_hash": "",
            },
            dry_run=True,
        )
        assert result.dry_run is True
        assert result.success is True
        connector.close()

    @respx.mock
    def test_requires_deploy_capability(self):
        connector = _make_connector()  # 只有 read_cloudflare_config
        with pytest.raises(PermissionError):
            connector.deploy_patch(
                {
                    "patch_id": "p1",
                    "source_path": "/old-page",
                    "target_url": "https://example.com/new-page",
                    "status_code": 301,
                },
                dry_run=True,
            )
        connector.close()

    @respx.mock
    def test_real_apply_requires_non_dry_run_policy(self):
        policy = SafetyPolicy(
            dry_run=True, allowed_capabilities={"read_cloudflare_config", "deploy_cloudflare_rules"}
        )
        connector = _make_connector(policy=policy)
        with pytest.raises(PermissionError):
            connector.deploy_patch(
                {
                    "patch_id": "p1",
                    "source_path": "/old-page",
                    "target_url": "https://example.com/new-page",
                    "status_code": 301,
                },
                dry_run=False,
            )
        connector.close()

    @respx.mock
    def test_rejects_target_url_outside_zone(self):
        policy = SafetyPolicy(allowed_capabilities={"read_cloudflare_config", "deploy_cloudflare_rules"})
        connector = _make_connector(policy=policy)

        result = connector.deploy_patch(
            {
                "patch_id": "p1",
                "source_path": "/old-page",
                "target_url": "https://totally-different.com/new-page",
                "status_code": 301,
                "base_ruleset_hash": "",
            },
            dry_run=True,
        )
        assert result.success is False
        assert "授權網域" in result.details
        connector.close()

    @respx.mock
    def test_rejects_http_target_url(self):
        policy = SafetyPolicy(allowed_capabilities={"read_cloudflare_config", "deploy_cloudflare_rules"})
        connector = _make_connector(policy=policy)

        result = connector.deploy_patch(
            {
                "patch_id": "p1",
                "source_path": "/old-page",
                "target_url": "http://example.com/new-page",
                "status_code": 301,
                "base_ruleset_hash": "",
            },
            dry_run=True,
        )
        assert result.success is False
        connector.close()

    @respx.mock
    def test_rejects_invalid_status_code(self):
        policy = SafetyPolicy(allowed_capabilities={"read_cloudflare_config", "deploy_cloudflare_rules"})
        connector = _make_connector(policy=policy)

        result = connector.deploy_patch(
            {
                "patch_id": "p1",
                "source_path": "/old-page",
                "target_url": "https://example.com/new-page",
                "status_code": 999,
                "base_ruleset_hash": "",
            },
            dry_run=True,
        )
        assert result.success is False
        connector.close()

    @respx.mock
    def test_real_apply_succeeds_and_adds_rule(self):
        policy = SafetyPolicy(
            dry_run=False, allowed_capabilities={"read_cloudflare_config", "deploy_cloudflare_rules"}
        )
        connector = _make_connector(policy=policy)

        respx.get(f"{_API}/zones/{_ZONE_ID}/rulesets/phases/http_request_dynamic_redirect/entrypoint").mock(
            return_value=httpx.Response(200, json={"success": True, "result": {"id": "rs1", "rules": []}})
        )
        put_route = respx.put(f"{_API}/zones/{_ZONE_ID}/rulesets/rs1").mock(
            return_value=httpx.Response(200, json={"success": True, "result": {"id": "rs1"}})
        )

        result = connector.deploy_patch(
            {
                "patch_id": "p1",
                "source_path": "/old-page",
                "target_url": "https://example.com/new-page",
                "status_code": 301,
                "base_ruleset_hash": "",
                "confirmation": connector.build_deploy_confirmation("p1"),
            },
            dry_run=False,
        )
        assert result.success is True
        assert put_route.called
        connector.close()

    @respx.mock
    def test_real_apply_rejects_missing_confirmation(self):
        """真寫入缺少確認字串時應拒絕，且不應發送任何寫入請求（獨立於
        SafetyPolicy 的 capability/dry_run 閘門之外的第二層防護）。"""
        policy = SafetyPolicy(
            dry_run=False, allowed_capabilities={"read_cloudflare_config", "deploy_cloudflare_rules"}
        )
        connector = _make_connector(policy=policy)

        get_route = respx.get(
            f"{_API}/zones/{_ZONE_ID}/rulesets/phases/http_request_dynamic_redirect/entrypoint"
        ).mock(return_value=httpx.Response(200, json={"success": True, "result": {"id": "rs1", "rules": []}}))

        result = connector.deploy_patch(
            {
                "patch_id": "p1",
                "source_path": "/old-page",
                "target_url": "https://example.com/new-page",
                "status_code": 301,
                "base_ruleset_hash": "",
            },
            dry_run=False,
        )
        assert result.success is False
        assert "確認字串" in result.details
        assert not get_route.called  # 連重新讀取 ruleset 都不該發生
        connector.close()

    @respx.mock
    def test_real_apply_rejects_wrong_confirmation(self):
        policy = SafetyPolicy(
            dry_run=False, allowed_capabilities={"read_cloudflare_config", "deploy_cloudflare_rules"}
        )
        connector = _make_connector(policy=policy)

        result = connector.deploy_patch(
            {
                "patch_id": "p1",
                "source_path": "/old-page",
                "target_url": "https://example.com/new-page",
                "status_code": 301,
                "base_ruleset_hash": "",
                "confirmation": "APPLY CLOUDFLARE wrong-zone.com p1",
            },
            dry_run=False,
        )
        assert result.success is False
        connector.close()

    @respx.mock
    def test_real_apply_rejects_when_ruleset_hash_mismatch(self):
        policy = SafetyPolicy(
            dry_run=False, allowed_capabilities={"read_cloudflare_config", "deploy_cloudflare_rules"}
        )
        connector = _make_connector(policy=policy)

        respx.get(f"{_API}/zones/{_ZONE_ID}/rulesets/phases/http_request_dynamic_redirect/entrypoint").mock(
            return_value=httpx.Response(
                200, json={"success": True, "result": {"id": "rs1", "rules": [{"ref": "someone_else_rule"}]}}
            )
        )

        with pytest.raises(CloudflareConflictError):
            connector.deploy_patch(
                {
                    "patch_id": "p1",
                    "source_path": "/old-page",
                    "target_url": "https://example.com/new-page",
                    "status_code": 301,
                    "base_ruleset_hash": "stale-hash-from-before",
                    "confirmation": connector.build_deploy_confirmation("p1"),
                },
                dry_run=False,
            )
        connector.close()


class TestRedaction:
    @respx.mock
    def test_auth_error_message_does_not_leak_token(self):
        respx.get(f"{_API}/user/tokens/verify").mock(
            return_value=httpx.Response(401, json={"success": False, "errors": []})
        )
        try:
            CloudflareConnector(_ZONE_ID, api_token="super-secret-token-value")
        except CloudflareAuthError as exc:
            assert "super-secret-token-value" not in str(exc)


class TestBuildRedirectAddPatchAndSnapshotHash:
    """build_snapshot()/build_redirect_add_patch() 讓呼叫端不需要自己
    計算 base_ruleset_hash 就能組出合法的 deploy_patch() 輸入。"""

    @respx.mock
    def test_build_snapshot_includes_ruleset_hash_info(self):
        _mock_token_verify_ok()
        _mock_zone_ok()
        respx.get(f"{_API}/zones/{_ZONE_ID}/dns_records").mock(
            return_value=httpx.Response(200, json={"success": True, "result": []})
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

        connector = CloudflareConnector(_ZONE_ID, api_token="test-token")
        snapshot = connector.build_snapshot()

        assert snapshot["redirect_ruleset"]["ruleset_id"] == "rs1"
        assert snapshot["redirect_ruleset"]["ruleset_hash"]
        assert snapshot["cache_ruleset"]["ruleset_id"] == "rs2"
        connector.close()

    @respx.mock
    def test_build_redirect_add_patch_produces_valid_deployable_patch(self):
        policy = SafetyPolicy(
            dry_run=False, allowed_capabilities={"read_cloudflare_config", "deploy_cloudflare_rules"}
        )
        connector = _make_connector(policy=policy)

        respx.get(f"{_API}/zones/{_ZONE_ID}/rulesets/phases/http_request_dynamic_redirect/entrypoint").mock(
            return_value=httpx.Response(200, json={"success": True, "result": {"id": "rs1", "rules": []}})
        )
        put_route = respx.put(f"{_API}/zones/{_ZONE_ID}/rulesets/rs1").mock(
            return_value=httpx.Response(200, json={"success": True, "result": {"id": "rs1"}})
        )

        patch = connector.build_redirect_add_patch(
            patch_id="p1", source_path="/old-page", target_url="https://example.com/new-page"
        )
        patch["confirmation"] = connector.build_deploy_confirmation("p1")

        result = connector.deploy_patch(patch, dry_run=False)
        assert result.success is True
        assert put_route.called
        connector.close()
