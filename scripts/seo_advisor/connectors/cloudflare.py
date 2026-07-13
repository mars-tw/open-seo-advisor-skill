"""CloudflareConnector：唯讀盤點 Cloudflare zone 的 DNS/redirect/cache 設定，
選配寫入能力只開放 redirect rule 的新增（其餘寫入動作留待後續版本）。

這份設計由 NORA（Codex）自主評估後定案（v0.3.0，延續 v0.2.6/v0.2.7 的
NORA 自主評估+落地+複審模式）：

- CloudflareConnector 的定位是「讀取/修改 CDN 層設定」，不是「網站內容
  爬蟲」。因此 `capabilities()` 不回報 `read_urls`；`list_urls()`/
  `fetch_url()` 完全不 override（維持 base class 的 `ConnectorCapabilityError`）
  ——這跟 WordPressAPIConnector/HTTPConnector 的定位刻意不同，不要混用。
- Cloudflare API 的請求目標固定是官方端點
  `https://api.cloudflare.com/client/v4`，不涉及使用者輸入的任意網址，
  因此不使用 `ensure_host_allowed()`（那是給「使用者輸入的目標網址」用
  的 SSRF 防護，這裡的威脅模型不同）。真正的風險是 zone_id 格式錯誤/
  拼接、token 洩漏、寫入造成站點中斷、對 API response 過度信任。
- 只支援 API Token 認證（不支援 Global API Key，Cloudflare 官方也建議
  棄用 Global Key，因為它的權限範圍是整個帳戶且無法限制單一 zone）。
- 讀取：zone profile、DNS records、redirect/cache rulesets（Rulesets
  API 的 `http_request_dynamic_redirect`/`http_request_cache_settings`
  phase）、legacy Page Rules（盡力讀取，不強依賴）。任何一個區塊因權限
  不足回 403，只記錄 permission note，不中斷整個 snapshot。
- 寫入：只開放 redirect rule 的 `add_rule`（見 `deploy_patch()`），且要求
  安全子集（來源路徑只能是 exact-match 絕對路徑，目標網址必須是 HTTPS
  且落在同一個 zone 的授權網域內）。寫入前重新讀取目前 ruleset 並比對
  hash，若與 patch 建立時的 base hash 不符就拒絕套用（避免覆蓋掉使用者
  在 Cloudflare Dashboard 上同時做的變更）。cache rule 寫入、Pages 部署
  刻意不做，留待後續版本獨立設計與審查。
"""

from __future__ import annotations

import hashlib
import json
import os

import httpx

from seo_advisor.connectors.base import ConnectorCapabilityError, WebsiteConnector
from seo_advisor.env_hints import set_env_var_hint
from seo_advisor.models import ConnectorProfile, DeployResult, SafetyPolicy
from seo_advisor.security.cloudflare_safety import (
    UnsafeRedirectRuleError,
    validate_redirect_source_path,
    validate_redirect_target_url,
    validate_zone_id,
)

_API_BASE = "https://api.cloudflare.com/client/v4"
_TOKEN_ENV_VAR = "CLOUDFLARE_API_TOKEN"

# API response 大小上限：Cloudflare 的設定類端點回應正常遠小於此，避免
# 異常巨大回應（例如帳戶下有大量 DNS record）吃爆記憶體。
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MiB

_REDIRECT_PHASE = "http_request_dynamic_redirect"
_CACHE_PHASE = "http_request_cache_settings"

# 這個 MVP 只支援的重導狀態碼；Cloudflare 允許 301/302/307/308。
_ALLOWED_REDIRECT_STATUS = frozenset({301, 302, 307, 308})

# 用來標記由本工具建立的 rule，方便使用者辨識、也方便未來版本用 ref 尋找
# 自己建立過的規則做管理（例如 disable）。
_RULE_REF_PREFIX = "open_seo_advisor_"


class CloudflareConnectorError(RuntimeError):
    """CloudflareConnector 操作失敗時的基底例外。"""


class CloudflareAuthError(CloudflareConnectorError):
    """401：API Token 無效或已過期。"""


class CloudflarePermissionError(CloudflareConnectorError):
    """403：Token 有效但權限不足以存取這個資源。"""


class CloudflareZoneNotFoundError(CloudflareConnectorError):
    """404：zone_id 不存在，或 Token 沒有這個 zone 的存取權限。"""


class CloudflareApiError(CloudflareConnectorError):
    """429/5xx/其他非預期的 API 錯誤。"""


class CloudflareConflictError(CloudflareConnectorError):
    """寫入前重新比對 ruleset hash 發現已被他人變更，拒絕覆蓋套用。"""


def _redacted(exc: Exception) -> str:
    from seo_advisor.errors import redact_secrets

    return redact_secrets(str(exc))


def _ruleset_hash(ruleset_json: dict) -> str:
    """對 ruleset 內容算出穩定 hash，用於樂觀鎖比對（避免寫入時覆蓋掉
    使用者剛好同時在 Cloudflare Dashboard 上做的變更）。"""
    canonical = json.dumps(ruleset_json, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CloudflareConnector(WebsiteConnector):
    """唯讀盤點 Cloudflare zone 設定，選配 redirect rule 新增能力。

    capabilities() 只回報 `{"read_cloudflare_config"}`；有明確授權寫入
    （policy.allowed_capabilities 含 `deploy_cloudflare_rules`）才額外
    回報 `{"deploy_cloudflare_rules"}`。`list_urls()`/`fetch_url()` 完全
    不 override，這個 connector 不是拿來爬網站內容用的。
    """

    def __init__(
        self,
        zone_id: str,
        *,
        api_token: str | None = None,
        zone_name: str | None = None,
        policy: SafetyPolicy | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.policy = policy or SafetyPolicy(allowed_capabilities={"read_cloudflare_config"})

        validate_zone_id(zone_id)
        self._zone_id = zone_id
        self._expected_zone_name = zone_name

        token = api_token or os.environ.get(_TOKEN_ENV_VAR)
        if not token:
            raise CloudflareConnectorError(
                f"找不到 Cloudflare API Token，請提供 api_token 參數或設定環境變數 "
                f"{_TOKEN_ENV_VAR}。{set_env_var_hint(_TOKEN_ENV_VAR, 'your-api-token')}"
            )
        self._token = token

        self._client = httpx.Client(
            base_url=_API_BASE,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout_seconds,
        )

        self._verify_token()
        self._zone_name = self._verify_zone()

    # ------------------------------------------------------------------
    # 底層 API 呼叫 helper
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, *, json_body: dict | None = None) -> dict:
        """發送一次 Cloudflare API 請求，回應大小受限，非 2xx 狀態碼轉成
        對應的專用例外，例外訊息一律經過 redact_secrets() 處理。
        """
        try:
            with self._client.stream(method, path, json=json_body) as resp:
                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > _MAX_RESPONSE_BYTES:
                        raise CloudflareApiError("Cloudflare API 回應內容超過大小上限，已中止讀取。")
                body = b"".join(chunks)
                status_code = resp.status_code
        except httpx.TimeoutException as exc:
            raise CloudflareApiError(f"Cloudflare API 請求逾時：{_redacted(exc)}") from exc
        except httpx.HTTPError as exc:
            raise CloudflareApiError(f"Cloudflare API 請求失敗：{_redacted(exc)}") from exc

        try:
            payload = json.loads(body.decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise CloudflareApiError(f"Cloudflare API 回應不是合法的 JSON：{path}") from exc

        if status_code == 401:
            raise CloudflareAuthError(
                "Cloudflare API Token 無效或已過期，請確認 Token 是否正確、是否已被撤銷。"
            )
        if status_code == 403:
            raise CloudflarePermissionError(
                f"Cloudflare API Token 權限不足，無法存取 {path}。"
                "請確認 Token 是否具備對應權限（例如 Zone Read / DNS Read / "
                "Rulesets Read / Dynamic URL Redirects Write）。"
            )
        if status_code == 404:
            raise CloudflareZoneNotFoundError(
                f"找不到資源：{path}（可能是 zone_id 不存在，或 Token 沒有這個 zone 的存取權限）。"
            )
        if status_code == 429:
            raise CloudflareApiError("Cloudflare API 請求過於頻繁（429），請稍後再試。")
        if status_code >= 500:
            raise CloudflareApiError(f"Cloudflare API 伺服器錯誤（{status_code}）：{path}")
        if not (200 <= status_code < 300):
            raise CloudflareApiError(f"Cloudflare API 回傳非預期的狀態碼 {status_code}：{path}")

        if not isinstance(payload, dict) or not payload.get("success", False):
            errors = payload.get("errors") if isinstance(payload, dict) else None
            raise CloudflareApiError(f"Cloudflare API 回報失敗：{path}，errors={errors}")

        return payload

    def _verify_token(self) -> None:
        self._request("GET", "/user/tokens/verify")

    def _verify_zone(self) -> str:
        payload = self._request("GET", f"/zones/{self._zone_id}")
        zone_name = payload.get("result", {}).get("name", "")
        if self._expected_zone_name and zone_name.lower() != self._expected_zone_name.lower():
            raise CloudflareConnectorError(
                f"zone_id 對應的網域是 {zone_name!r}，與提供的 zone_name "
                f"{self._expected_zone_name!r} 不一致。為避免操作到錯誤的網域，已拒絕繼續。"
            )
        return zone_name

    # ------------------------------------------------------------------
    # WebsiteConnector 介面
    # ------------------------------------------------------------------

    def id(self) -> str:
        return f"cloudflare:{self._zone_name or self._zone_id}"

    def capabilities(self) -> set[str]:
        caps = {"read_cloudflare_config"}
        if "deploy_cloudflare_rules" in self.policy.allowed_capabilities:
            caps.add("deploy_cloudflare_rules")
        return caps

    def probe(self) -> ConnectorProfile:
        notes = [f"已連線至 Cloudflare zone：{self._zone_name}（{self._zone_id}）"]
        return ConnectorProfile(source_type="cloudflare", detected_stack=None, notes=notes)

    def list_urls(self, seed: str, limit: int) -> list:
        """CloudflareConnector 不是網站內容爬蟲，不支援 read_urls——
        `list_urls`/`fetch_url` 在 `WebsiteConnector` 是強制實作的
        abstract method（不像 `write_file`/`get_logs` 有預設實作可以
        略過不 override），因此這裡明確 override 並拋出
        `ConnectorCapabilityError`，而不是假裝支援。請改用
        `HTTPConnector` 掃描實際網站內容，或用 `build_snapshot()`/
        `list_dns_records()` 等專屬方法讀取 Cloudflare 的 CDN 層設定。
        """
        raise ConnectorCapabilityError(
            f"{self.id()} 不支援 list_urls()，CloudflareConnector 只讀取/修改 CDN 層設定"
            "（DNS/redirect/cache 規則），不是網站內容爬蟲。請改用 HTTPConnector。"
        )

    def fetch_url(self, url: str, *, render: bool = False, fetched_at: str = ""):
        raise ConnectorCapabilityError(
            f"{self.id()} 不支援 fetch_url()，CloudflareConnector 只讀取/修改 CDN 層設定"
            "（DNS/redirect/cache 規則），不是網站內容爬蟲。請改用 HTTPConnector。"
        )

    # ------------------------------------------------------------------
    # 唯讀盤點：DNS / rulesets / page rules
    # ------------------------------------------------------------------

    def list_dns_records(self) -> list[dict]:
        self.policy.require_capability("read_cloudflare_config", connector_id=self.id())
        try:
            payload = self._request("GET", f"/zones/{self._zone_id}/dns_records")
        except CloudflarePermissionError:
            return []
        return payload.get("result", [])

    def _list_rules_for_phase(self, phase: str) -> tuple[list[dict], str | None]:
        """回傳 (rules, ruleset_id)；權限不足時回傳空清單與 None，
        呼叫端據此記錄 permission note 而非中斷整個 snapshot。
        """
        try:
            payload = self._request(
                "GET", f"/zones/{self._zone_id}/rulesets/phases/{phase}/entrypoint"
            )
        except (CloudflarePermissionError, CloudflareZoneNotFoundError):
            return [], None
        result = payload.get("result", {})
        return result.get("rules", []), result.get("id")

    @staticmethod
    def _ruleset_snapshot_dict(phase: str, rules: list[dict], ruleset_id: str | None) -> dict:
        return {
            "phase": phase,
            "ruleset_id": ruleset_id,
            "rules_count": len(rules),
            "ruleset_hash": _ruleset_hash({"rules": rules}),
        }

    def get_ruleset_snapshot(self, phase: str) -> dict:
        """回傳指定 phase 的 ruleset 快照，含 `ruleset_id`/`rules_count`/
        `ruleset_hash`——這是 `build_redirect_add_patch()` 用來組出合法
        `deploy_patch()` 輸入的資料來源，呼叫端不需要自己計算 hash。
        """
        rules, ruleset_id = self._list_rules_for_phase(phase)
        return self._ruleset_snapshot_dict(phase, rules, ruleset_id)

    def list_page_rules(self) -> list[dict]:
        self.policy.require_capability("read_cloudflare_config", connector_id=self.id())
        try:
            payload = self._request("GET", f"/zones/{self._zone_id}/pagerules")
        except CloudflarePermissionError:
            return []
        return payload.get("result", [])

    def build_snapshot(self) -> dict:
        """回傳這個 zone 目前的完整設定快照：DNS records、redirect/cache
        rules、legacy page rules，以及 `redirect_ruleset`/`cache_ruleset`
        的 hash 資訊（供 `build_redirect_add_patch()` 組出合法的
        `deploy_patch()` 輸入，呼叫端不需要自己計算 hash）。任一區塊因
        權限不足而讀不到，記錄在 `permission_notes` 而不是讓整個呼叫失敗。
        """
        self.policy.require_capability("read_cloudflare_config", connector_id=self.id())

        permission_notes: list[str] = []

        dns_records = self.list_dns_records()
        if not dns_records:
            permission_notes.append("DNS records 可能因權限不足而無法讀取（或該 zone 沒有任何記錄）。")

        redirect_rules, redirect_ruleset_id = self._list_rules_for_phase(_REDIRECT_PHASE)
        cache_rules, cache_ruleset_id = self._list_rules_for_phase(_CACHE_PHASE)
        page_rules = self.list_page_rules()

        return {
            "zone_id": self._zone_id,
            "zone_name": self._zone_name,
            "dns_records": dns_records,
            "redirect_rules": redirect_rules,
            "cache_rules": cache_rules,
            "redirect_ruleset": self._ruleset_snapshot_dict(
                _REDIRECT_PHASE, redirect_rules, redirect_ruleset_id
            ),
            "cache_ruleset": self._ruleset_snapshot_dict(_CACHE_PHASE, cache_rules, cache_ruleset_id),
            "page_rules": page_rules,
            "permission_notes": permission_notes,
        }

    def build_redirect_add_patch(
        self,
        *,
        patch_id: str,
        source_path: str,
        target_url: str,
        status_code: int = 301,
        preserve_query_string: bool = True,
    ) -> dict:
        """組出一個可以直接傳給 `deploy_patch()` 的合法 patch dict：自動
        帶入目前 redirect ruleset 的 `base_ruleset_hash`（呼叫端不需要
        自己讀取 snapshot 再手算 hash，降低誤用成新增規則但漏帶 hash
        導致樂觀鎖形同虛設的風險）。
        """
        ruleset = self.get_ruleset_snapshot(_REDIRECT_PHASE)
        return {
            "patch_id": patch_id,
            "source_path": source_path,
            "target_url": target_url,
            "status_code": status_code,
            "preserve_query_string": preserve_query_string,
            "base_ruleset_hash": ruleset["ruleset_hash"],
        }

    # ------------------------------------------------------------------
    # 選配寫入：redirect rule 新增（唯一支援的真寫入操作）
    # ------------------------------------------------------------------

    def build_deploy_confirmation(self, patch_id: str) -> str:
        return f"APPLY CLOUDFLARE {self._zone_name} {patch_id}"

    def deploy_patch(self, patch: dict, dry_run: bool = True) -> DeployResult:
        """新增一條 redirect rule。`patch` 必須包含：
        - `source_path`：來源路徑（絕對路徑，exact-match，見
          security/cloudflare_safety.py 的驗證規則）
        - `target_url`：目標網址（必須 HTTPS，且 host 落在這個 zone 的
          授權網域內）
        - `status_code`：301/302/307/308 之一
        - `patch_id`：這次操作的識別字串，用於確認字串比對
        - `base_ruleset_hash`：呼叫端先前讀取 ruleset 時算出的 hash，
          若目前實際 hash 不符就拒絕套用（避免覆蓋掉他人剛做的變更）
        - `preserve_query_string`：可選，預設 True
        - `confirmation`：真寫入（dry_run=False）時必填，必須精確等於
          `build_deploy_confirmation(patch_id)` 的回傳值——這個檢查獨立於
          `SafetyPolicy` 的 capability/dry_run 閘門，即使呼叫端直接呼叫
          connector 的 `deploy_patch()`（不經過 CLI 的互動確認流程），
          也不會在沒有明確確認的情況下真的修改 DNS/redirect 設定
          （這類操作若出錯，可能導致整個網站無法存取，風險不低於
          SSHConnector 的遠端操作，因此比照同樣的二次確認機制）。

        只支援新增規則（`add_rule`），不支援修改/刪除既有規則、不支援
        cache rule 寫入、不支援 Cloudflare Pages 部署——這些留待後續
        版本獨立設計與審查。
        """
        self.policy.require_capability("deploy_cloudflare_rules", connector_id=self.id())
        if not dry_run:
            self.policy.require_write(connector_id=self.id())

        source_path = patch.get("source_path", "")
        target_url = patch.get("target_url", "")
        status_code = patch.get("status_code")
        patch_id = patch.get("patch_id", "")
        base_ruleset_hash = patch.get("base_ruleset_hash", "")
        preserve_query_string = patch.get("preserve_query_string", True)
        confirmation = patch.get("confirmation")

        if not dry_run:
            expected_confirmation = self.build_deploy_confirmation(patch_id)
            if not confirmation or confirmation.strip() != expected_confirmation:
                return DeployResult(
                    dry_run=False,
                    success=False,
                    details=(
                        f"缺少或錯誤的確認字串。真寫入 redirect rule 需要在 patch 內提供 "
                        f'confirmation={expected_confirmation!r}，確認你明確授權這次變更'
                        "（DNS/redirect 設定寫入若出錯可能導致網站無法存取，因此要求二次確認）。"
                    ),
                )

        try:
            validate_redirect_source_path(source_path)
            allowed_hosts = frozenset({self._zone_name.lower(), f"www.{self._zone_name.lower()}"})
            validate_redirect_target_url(target_url, allowed_hosts=allowed_hosts)
        except UnsafeRedirectRuleError as exc:
            return DeployResult(dry_run=dry_run, success=False, details=str(exc))

        if status_code not in _ALLOWED_REDIRECT_STATUS:
            return DeployResult(
                dry_run=dry_run,
                success=False,
                details=f"status_code 必須是 {sorted(_ALLOWED_REDIRECT_STATUS)} 其中之一。",
            )

        rule_ref = f"{_RULE_REF_PREFIX}{patch_id}"
        rule_draft = {
            "ref": rule_ref,
            "description": f"Open SEO Advisor redirect: {source_path} -> {target_url}",
            "expression": f'http.request.uri.path eq "{source_path}"',
            "action": "redirect",
            "action_parameters": {
                "from_value": {
                    "status_code": status_code,
                    "target_url": {"value": target_url},
                    "preserve_query_string": bool(preserve_query_string),
                }
            },
        }

        if dry_run:
            return DeployResult(
                dry_run=True,
                success=True,
                details=f"dry-run：將新增 redirect rule {source_path} -> {target_url}"
                f"（HTTP {status_code}），尚未實際寫入。",
            )

        # 真寫入前重新讀取目前的 ruleset，比對 hash 避免覆蓋掉使用者在
        # Cloudflare Dashboard 上同時做的變更（樂觀鎖）。
        current_rules, ruleset_id = self._list_rules_for_phase(_REDIRECT_PHASE)
        current_hash = _ruleset_hash({"rules": current_rules})
        if base_ruleset_hash and current_hash != base_ruleset_hash:
            raise CloudflareConflictError(
                "目前的 redirect ruleset 內容與套用計畫建立時的快照不一致"
                "（可能有人在 Cloudflare Dashboard 上同時做了變更），為避免覆蓋，"
                "已拒絕套用。請重新讀取最新設定後再產生新的套用計畫。"
            )

        updated_rules = [*current_rules, rule_draft]

        if ruleset_id:
            result_payload = self._request(
                "PUT",
                f"/zones/{self._zone_id}/rulesets/{ruleset_id}",
                json_body={"rules": updated_rules},
            )
        else:
            result_payload = self._request(
                "POST",
                f"/zones/{self._zone_id}/rulesets",
                json_body={
                    "name": "Open SEO Advisor redirect rules",
                    "kind": "zone",
                    "phase": _REDIRECT_PHASE,
                    "rules": updated_rules,
                },
            )

        new_ruleset_id = result_payload.get("result", {}).get("id", ruleset_id or "")
        return DeployResult(
            dry_run=False,
            success=True,
            details=f"已新增 redirect rule {source_path} -> {target_url}"
            f"（HTTP {status_code}），ruleset_id={new_ruleset_id}，rule ref={rule_ref}。",
        )

    def close(self) -> None:
        self._client.close()
