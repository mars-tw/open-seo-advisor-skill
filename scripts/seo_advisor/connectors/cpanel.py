"""CPanelConnector：透過 cPanel UAPI Fileman 唯讀盤點網站靜態檔案，選配
有限度的寫入能力（只限極窄的靜態 SEO 資產）。

這份設計由 NORA（Codex）自主評估後定案（v0.3.0，延續 CloudflareConnector
的 NORA 自主評估+落地+複審模式）：

- 定位聚焦「透過 cPanel UAPI 讀寫網站檔案」，不做帳戶層級設定管理
  （DNS/Email/Cron/Database/SSL/PHP 設定一律不做，那些風險與範圍完全
  超出 SEO 診斷工具該碰的範圍）。
- 只支援 cPanel API Token 認證（不支援帳密），只支援 UAPI（不支援較舊的
  API2，避免維護兩套語意）。
- cPanel host 是使用者輸入的（不像 Cloudflare API host 是寫死的官方
  端點），因此走 `ensure_host_allowed()` SSRF 防護，跟 SSHConnector/
  WordPressAPIConnector 同樣的威脅模型；預設要求 HTTPS + TLS 驗證。
- 遠端路徑一律用 component-wise walk 防 symlink jail escape（見
  security/cpanel_path_safety.py），但因為 cPanel UAPI 沒有 SFTP 的
  lstat() 對應操作，改用「逐層列目錄比對子項目 type」的方式達成同樣
  目的（每一步都看到「這一步本身」的真實類型，不能被中途 follow 過去）。
- 讀取白名單/敏感檔名 denylist 與 SSHConnector 共用同一套規則（見
  security/remote_file_policy.py）。
- 寫入能力刻意收得極窄：只允許 `.html`/`.htm`/`.txt`/`.xml` 這類靜態
  SEO 資產，明確拒絕 `.php`/`.js`/`.css`/`.htaccess`/`web.config` 等
  可能影響網站行為或安全設定的檔案；寫入前一律先備份到本機；真寫入需要
  確認字串（比照 SSHConnector/CloudflareConnector 的二次確認設計）。
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import deque
from pathlib import Path
from urllib.parse import urlparse

import httpx

from seo_advisor.connectors.base import WebsiteConnector
from seo_advisor.env_hints import set_env_var_hint
from seo_advisor.models import (
    BackupResult,
    ConnectorProfile,
    FileRecord,
    PageSnapshot,
    PatchResult,
    SafetyPolicy,
    UrlRecord,
)
from seo_advisor.security.cpanel_path_safety import (
    RemoteFileEntry,
    RemoteFileNotFoundError,
    UnsafeRemotePathError,
    ensure_remote_root_allowed,
    resolve_remote_path,
)
from seo_advisor.security.network_policy import ensure_host_allowed, is_cloud_metadata_host
from seo_advisor.security.remote_file_policy import is_read_target_allowed

_TOKEN_ENV_VAR = "CPANEL_API_TOKEN"

# 單一檔案讀取大小上限，避免超大檔案吃爆記憶體或造成過長的連線佔用。
_MAX_READ_BYTES = 10 * 1024 * 1024  # 10 MB
# 寫入的單一檔案大小上限：比讀取更保守，這輪只用於小型靜態 SEO 資產
# （robots.txt/sitemap.xml/單頁 HTML），不是拿來上傳大型檔案的工具。
_MAX_WRITE_BYTES = 2 * 1024 * 1024  # 2 MiB
# API response 大小上限（cPanel UAPI 回應通常遠小於此）。
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MiB

# list_urls() 遞迴掃描 remote_root 的三重上限：跟 SSHConnector 一致的
# 防護理由——每層 list_files 都有網路延遲，不能無上限遞迴。
_MAX_SCAN_DEPTH = 5
_MAX_FILES_SCANNED = 2000
_MAX_DIRS_SCANNED = 500

# component-wise walk 每一層都要下載該層目錄的完整內容（cPanel UAPI 沒有
# 「只查單一項目是否存在」的端點），若某一層目錄項目數量異常龐大，即使
# 只是要解析一個檔案路徑也會產生巨大回應。這個上限拒絕異常寬的目錄，
# 避免把 component-wise walk 的安全設計變成資源耗盡的攻擊面。
_MAX_DIR_ENTRIES = 5000

_SKIPPED_DIR_NAMES = frozenset({
    ".git", ".svn", ".seo-advisor", "node_modules", "vendor",
    "dist", "cache", "tmp", "backup",
})

# 允許寫入的副檔名：比讀取白名單更窄，這是「有限度部署能力」的核心限制
# ——明確排除任何可能影響網站行為或安全設定的檔案類型。
_ALLOWED_WRITE_EXTENSIONS = frozenset({".html", ".htm", ".txt", ".xml"})
_FORBIDDEN_WRITE_BASENAMES = frozenset({".htaccess", "web.config", ".user.ini", "wp-config.php"})


class CPanelConnectorError(RuntimeError):
    """CPanelConnector 相關操作失敗時的基底例外。"""


class CPanelAuthError(CPanelConnectorError):
    """401/403：API Token 或使用者名稱錯誤。"""


class CPanelPermissionError(CPanelConnectorError):
    """UAPI Fileman 端點被主機商禁用，或帳號沒有對應權限。"""


class CPanelApiError(CPanelConnectorError):
    """其他 UAPI 錯誤（逾時、非預期回應格式、伺服器錯誤等）。"""


def _redacted(exc: Exception) -> str:
    from seo_advisor.errors import redact_secrets

    return redact_secrets(str(exc))


class CPanelConnector(WebsiteConnector):
    """透過 cPanel UAPI Fileman 唯讀盤點網站靜態檔案，選配寫入極窄的靜態
    SEO 資產。capabilities() 只回報 `{"read_files", "read_urls"}`，有
    `enable_write=True` 且 policy 授權才加 `{"write_files"}`。
    """

    def __init__(
        self,
        host: str,
        *,
        username: str,
        remote_root: str = "public_html",
        api_token: str | None = None,
        port: int = 2083,
        policy: SafetyPolicy | None = None,
        confirm_connect: str | None = None,
        allow_private_network: bool = False,
        enable_write: bool = False,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.policy = policy or SafetyPolicy(allowed_capabilities={"read_files", "read_urls"})
        self._host = host
        self._port = port
        self._username = username
        self._enable_write = enable_write

        expected_confirm = self.build_connect_confirmation()
        if confirm_connect is None or confirm_connect.strip().upper() != expected_confirm.upper():
            raise CPanelConnectorError(
                f"連線前需要明確確認。請提供 confirm_connect={expected_confirm!r}，"
                "確認你有權對這個 cPanel 帳號執行 SEO 診斷讀取（或寫入）。"
            )

        token = api_token or os.environ.get(_TOKEN_ENV_VAR)
        if not token:
            raise CPanelConnectorError(
                f"找不到 cPanel API Token，請提供 api_token 參數或設定環境變數 "
                f"{_TOKEN_ENV_VAR}。{set_env_var_hint(_TOKEN_ENV_VAR, 'your-api-token')}"
            )
        self._token = token

        base_url = f"https://{host}:{port}"
        parsed = urlparse(base_url)
        if not parsed.hostname:
            raise CPanelConnectorError(f"host {host!r} 不是合法的主機名稱。")
        ensure_host_allowed(base_url, allow_private_network=allow_private_network)
        if is_cloud_metadata_host(parsed.hostname):
            raise CPanelConnectorError(
                f"目標 {host!r} 是雲端 metadata 位址，CPanelConnector 永遠拒絕連線到這類位址。"
            )

        ensure_remote_root_allowed(remote_root)
        self._remote_root = remote_root.strip().rstrip("/")

        self._base_url = base_url
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"cpanel {username}:{token}"},
            timeout=timeout_seconds,
        )

        self._verify_connection()

    def build_connect_confirmation(self) -> str:
        return f"CONNECT CPANEL {self._host}:{self._port}"

    def build_write_confirmation(self, path: str) -> str:
        return f"APPLY CPANEL {self._host} {path}"

    # ------------------------------------------------------------------
    # 底層 API 呼叫
    # ------------------------------------------------------------------

    def _uapi_call(self, module: str, function: str, *, params: dict | None = None) -> dict:
        """呼叫 cPanel UAPI 的 `<module>::<function>`，回應大小受限，非
        預期的狀態碼/回應格式轉成對應例外，例外訊息一律經過 redact_secrets()
        處理。
        """
        path = f"/execute/{module}/{function}"
        try:
            with self._client.stream("GET", path, params=params) as resp:
                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > _MAX_RESPONSE_BYTES:
                        raise CPanelApiError("cPanel UAPI 回應內容超過大小上限，已中止讀取。")
                body = b"".join(chunks)
                status_code = resp.status_code
        except httpx.TimeoutException as exc:
            raise CPanelApiError(f"cPanel UAPI 請求逾時：{_redacted(exc)}") from exc
        except httpx.HTTPError as exc:
            raise CPanelApiError(f"cPanel UAPI 請求失敗：{_redacted(exc)}") from exc

        if status_code in (401, 403):
            raise CPanelAuthError(
                "cPanel API Token 或使用者名稱錯誤，或 Token 已被撤銷。"
                "請確認 Authorization header 使用格式：cpanel <username>:<api_token>。"
            )
        if status_code == 404:
            raise CPanelPermissionError(
                f"找不到 UAPI 端點 {module}::{function}，主機商可能已停用此功能。"
            )
        if status_code >= 500:
            raise CPanelApiError(f"cPanel 伺服器錯誤（{status_code}）：{module}::{function}")
        if status_code != 200:
            raise CPanelApiError(f"cPanel UAPI 回傳非預期的狀態碼 {status_code}：{module}::{function}")

        try:
            payload = json.loads(body.decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise CPanelApiError(f"cPanel UAPI 回應不是合法的 JSON：{module}::{function}") from exc

        status = payload.get("status")
        if status == 0:
            errors = payload.get("errors") or []
            error_text = "; ".join(str(e) for e in errors) if errors else "未知錯誤"
            if "permission" in error_text.lower() or "disabled" in error_text.lower():
                raise CPanelPermissionError(f"cPanel UAPI 拒絕請求：{error_text}")
            raise CPanelApiError(f"cPanel UAPI 回報失敗：{error_text}")

        return payload

    def _verify_connection(self) -> None:
        self._uapi_call("Fileman", "list_files", params={"dir": self._remote_root})

    # ------------------------------------------------------------------
    # WebsiteConnector 介面
    # ------------------------------------------------------------------

    def id(self) -> str:
        return f"cpanel:{self._username}@{self._host}:{self._port}"

    def capabilities(self) -> set[str]:
        caps = {"read_files", "read_urls"}
        if self._enable_write and "write_files" in self.policy.allowed_capabilities:
            caps.add("write_files")
        return caps

    def probe(self) -> ConnectorProfile:
        notes = [
            f"已連線：{self._username}@{self._host}:{self._port}",
            f"授權範圍（remote_root）：{self._remote_root}",
        ]
        return ConnectorProfile(source_type="cpanel", detected_stack=None, notes=notes)

    # ------------------------------------------------------------------
    # 目錄列舉 / component-wise path resolve
    # ------------------------------------------------------------------

    def _list_dir(self, directory: str) -> list[RemoteFileEntry]:
        payload = self._uapi_call("Fileman", "list_files", params={"dir": directory})
        raw_entries = payload.get("data") or []
        if len(raw_entries) > _MAX_DIR_ENTRIES:
            raise CPanelConnectorError(
                f"目錄 {directory!r} 項目數量（{len(raw_entries)}）超過上限"
                f"（{_MAX_DIR_ENTRIES}），為避免資源耗盡已拒絕處理。"
            )
        entries: list[RemoteFileEntry] = []
        for item in raw_entries:
            name = item.get("file", "")
            if name in (".", ".."):
                continue
            file_type = str(item.get("type", "")).lower()
            entries.append(
                RemoteFileEntry(
                    path=f"{directory.rstrip('/')}/{name}",
                    is_dir=file_type == "dir",
                    is_link=file_type in ("link", "symlink"),
                    size=int(item.get("size", 0) or 0),
                )
            )
        return entries

    def _resolve(self, path: str) -> RemoteFileEntry:
        return resolve_remote_path(self._list_dir, self._remote_root, path)

    # ------------------------------------------------------------------
    # read_files capability
    # ------------------------------------------------------------------

    def list_files(self, path: str) -> list[FileRecord]:
        self.policy.require_capability("read_files", connector_id=self.id())

        if path:
            target = self._resolve(path)
            remote_dir = f"{self._remote_root.rstrip('/')}/{target.path}"
        else:
            remote_dir = self._remote_root

        records: list[FileRecord] = []
        for entry in self._list_dir(remote_dir):
            if entry.is_link:
                # 列出但不 follow：呼叫端若嘗試 read_file 這個路徑，
                # resolve_remote_path 會在解析階段再次拒絕。
                continue
            basename = entry.path.rsplit("/", 1)[-1]
            rel_prefix = f"{path.rstrip('/')}/" if path else ""
            records.append(
                FileRecord(path=f"{rel_prefix}{basename}", size_bytes=entry.size, is_dir=entry.is_dir)
            )
        return records

    def read_file(self, path: str) -> bytes:
        self.policy.require_capability("read_files", connector_id=self.id())

        if not is_read_target_allowed(path):
            raise UnsafeRemotePathError(
                f"{path!r} 不在允許讀取的副檔名範圍內，或檔名符合敏感檔名 denylist，已拒絕讀取。"
            )

        resolved = self._resolve(path)
        if resolved.is_dir:
            raise UnsafeRemotePathError(f"{path!r} 是目錄，不是檔案，無法讀取。")
        if resolved.size > _MAX_READ_BYTES:
            raise CPanelConnectorError(
                f"{path!r} 大小（{resolved.size} bytes）超過上限（{_MAX_READ_BYTES} bytes），拒絕讀取。"
            )

        remote_path = f"{self._remote_root.rstrip('/')}/{resolved.path}"
        payload = self._uapi_call(
            "Fileman", "get_file_content", params={"dir": self._remote_root, "file": remote_path}
        )
        content_text = payload.get("data", {}).get("content", "")
        content = content_text.encode("utf-8")
        if len(content) > _MAX_READ_BYTES:
            raise CPanelConnectorError(f"{path!r} 讀取內容超過大小上限，已中止讀取。")
        return content

    # ------------------------------------------------------------------
    # read_urls capability：把遠端檔案系統包裝成 URL 爬取介面
    # ------------------------------------------------------------------

    def list_urls(self, seed: str, limit: int) -> list[UrlRecord]:
        records: list[UrlRecord] = []
        dirs_scanned = 0
        queue: deque[tuple[str, int]] = deque([("", 0)])

        while queue and len(records) < limit:
            if dirs_scanned >= _MAX_DIRS_SCANNED:
                break
            rel_dir, depth = queue.popleft()
            dirs_scanned += 1

            try:
                entries = self.list_files(rel_dir)
            except (RemoteFileNotFoundError, UnsafeRemotePathError):
                continue

            # cPanel UAPI 的 list_files 一次回傳整個目錄內容（沒有分頁機制，
            # 不像 SSHConnector 的 SFTP listdir 需要考慮分批讀取），因此
            # 這裡不需要 SSHConnector 那種「提早停止分頁」的邏輯。
            for entry in entries:
                if len(records) >= limit or len(records) >= _MAX_FILES_SCANNED:
                    break
                basename = entry.path.rsplit("/", 1)[-1]
                if entry.is_dir:
                    if basename in _SKIPPED_DIR_NAMES:
                        continue
                    if depth + 1 <= _MAX_SCAN_DEPTH:
                        queue.append((entry.path, depth + 1))
                    continue
                if entry.path.lower().endswith((".html", ".htm")):
                    records.append(UrlRecord(url=f"/{entry.path}", source="crawl", discovered_depth=depth))

        return records[:limit]

    def fetch_url(self, url: str, *, render: bool = False, fetched_at: str = "") -> PageSnapshot:
        if render:
            raise NotImplementedError("CPanelConnector 不支援 render=True（無 headless browser）。")

        rejection = _reject_unsafe_fetch_url(url)
        if rejection is not None:
            return PageSnapshot(
                url=url, status_code=0, final_url=url, headers={}, html="", fetched_at=fetched_at,
                fetch_error_type="unsafe_remote_path", fetch_error_message=rejection,
            )

        rel_path = url.lstrip("/")
        try:
            content = self.read_file(rel_path)
        except (RemoteFileNotFoundError, FileNotFoundError):
            return PageSnapshot(
                url=url, status_code=404, final_url=url, headers={}, html="", fetched_at=fetched_at
            )
        except UnsafeRemotePathError as exc:
            return PageSnapshot(
                url=url, status_code=0, final_url=url, headers={}, html="", fetched_at=fetched_at,
                fetch_error_type="unsafe_remote_path", fetch_error_message=str(exc),
            )

        html = content.decode("utf-8", errors="replace")
        return PageSnapshot(
            url=url, status_code=200, final_url=url, headers={}, html=html, fetched_at=fetched_at
        )

    # ------------------------------------------------------------------
    # 選配寫入：極窄的靜態 SEO 資產
    # ------------------------------------------------------------------

    def _backup_dir_name(self) -> str:
        """把 host 轉成安全的本機目錄名稱：host 字串本身可能含有檔案系統
        不允許的字元，直接當目錄名稱使用有風險；用「安全字元子集 + 完整
        host 的 hash」組合，同時保留可讀性與避免特殊字元/大小寫碰撞問題。
        """
        safe_chars = "".join(ch if ch.isalnum() or ch in ("-", ".") else "_" for ch in self._host)
        host_hash = hashlib.sha256(self._host.encode("utf-8")).hexdigest()[:12]
        return f"{safe_chars[:80]}-{host_hash}"

    def backup(self, targets: list[str]) -> BackupResult:
        """把即將被修改的檔案內容備份到本機（不是遠端），供 write_file()
        失敗或使用者事後需要回滾時參考。
        """
        self.policy.require_capability("write_files", connector_id=self.id())

        backup_dir = Path.home() / ".seo-advisor" / "cpanel-backups" / self._backup_dir_name()
        backup_dir.mkdir(parents=True, exist_ok=True)
        manifest: dict[str, dict] = {}

        for target in targets:
            try:
                content = self.read_file(target)
                existed = True
            except (RemoteFileNotFoundError, FileNotFoundError):
                content = b""
                existed = False

            safe_name = target.replace("/", "__")
            if existed:
                (backup_dir / safe_name).write_bytes(content)
            manifest[target] = {
                "existed_before": existed,
                "sha256": hashlib.sha256(content).hexdigest() if existed else None,
                "size": len(content) if existed else 0,
            }

        manifest_path = backup_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        return BackupResult(targets=targets, backup_path=str(backup_dir))

    def write_file(self, path: str, content: bytes, dry_run: bool = True) -> PatchResult:
        """寫入極窄範圍的靜態 SEO 資產。cPanel UAPI 的 `save_file_content`
        不保證 POSIX atomic write，這是已知的正確性層面殘餘（不是安全
        層面問題）。
        """
        self.policy.require_capability("write_files", connector_id=self.id())
        if not dry_run:
            self.policy.require_write(connector_id=self.id())

        basename = path.rsplit("/", 1)[-1].lower()
        suffix = "." + basename.rsplit(".", 1)[-1] if "." in basename else ""
        if basename in _FORBIDDEN_WRITE_BASENAMES or suffix not in _ALLOWED_WRITE_EXTENSIONS:
            raise UnsafeRemotePathError(
                f"{path!r} 不在允許寫入的副檔名範圍內（僅允許 "
                f"{sorted(_ALLOWED_WRITE_EXTENSIONS)}），已拒絕寫入。"
            )
        if len(content) > _MAX_WRITE_BYTES:
            raise CPanelConnectorError(
                f"{path!r} 內容大小超過寫入上限（{_MAX_WRITE_BYTES} bytes），已拒絕寫入。"
            )

        components_path = path.lstrip("/")
        try:
            existing = self._resolve(components_path)
            if existing.is_dir:
                raise UnsafeRemotePathError(f"{path!r} 是目錄，無法寫入。")
        except RemoteFileNotFoundError:
            pass  # 檔案不存在時視為新建，路徑語法本身已經過驗證。

        diff_preview = f"（{len(content)} bytes 將寫入 {path}）"

        if dry_run:
            return PatchResult(path=path, dry_run=True, diff=diff_preview, applied=False)

        remote_path = f"{self._remote_root.rstrip('/')}/{components_path}"
        self._uapi_call(
            "Fileman", "save_file_content",
            params={
                "dir": self._remote_root,
                "file": remote_path,
                "content": content.decode("utf-8", errors="replace"),
            },
        )
        return PatchResult(path=path, dry_run=False, diff=diff_preview, applied=True)

    def close(self) -> None:
        self._client.close()


def _reject_unsafe_fetch_url(url: str) -> str | None:
    """檢查 fetch_url() 收到的 url 是否為合法的 path-like 輸入（跟
    SSHConnector 的同名函式邏輯一致：只接受純路徑，拒絕 query/fragment/
    scheme/userinfo，不靜默 strip）。
    """
    if "?" in url or "#" in url:
        return f"{url!r} 含有 query string 或 fragment，CPanelConnector 只接受純路徑，已拒絕。"
    parsed = urlparse(url)
    if parsed.scheme:
        return f"{url!r} 含有 scheme（{parsed.scheme}:），CPanelConnector 只接受相對路徑，已拒絕。"
    if parsed.username or parsed.password:
        return f"{url!r} 含有帳號密碼資訊，已拒絕。"
    return None
