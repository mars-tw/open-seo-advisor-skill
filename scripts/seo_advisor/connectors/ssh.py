"""SSHConnector：透過 SFTP 唯讀存取使用者已授權的遠端伺服器，讀取網站的
靜態檔案（HTML/robots.txt/sitemap.xml 等）以支援 SEO 診斷。

這份設計經過 NORA（Codex）與 Grok 兩個獨立模型三輪交叉審查定案，MVP 範圍
刻意收得比最初規劃更窄：

- 做 `read_files`（`list_files`/`read_file`）與 `read_urls`
  （`list_urls`/`fetch_url`，把遠端檔案系統包裝成 URL 爬取介面供
  `crawl_site()` 使用），capabilities() 誠實回報實際支援的能力。
- `read_logs`（`get_logs`）為選配能力：只有建構時明確提供
  `allowed_log_paths` 才會回報這個能力，log 走獨立於 remote_root 的
  檔案白名單機制（見 security/ssh_log_safety.py），因為 log 路徑天然
  常在網站 remote_root 之外。
- 不做 `write_files`/`run_commands`：完全不 override，維持
  WebsiteConnector base class 的 NotImplementedError，避免「保留 gate
  但邏輯是空殼」的半套實作在未來被誤接上。
- 不支援密碼認證、不支援 jump host/ProxyCommand/agent forwarding、
  不支援 sudo。

安全機制（詳見 docs/connector_contract.md 與 security/ssh_path_safety.py）：
- 認證優先序：SSH agent > 指定 key path；不支援密碼認證。
- Host key 一律驗證，使用本機 known_hosts，未知主機直接拒絕（不提供
  AutoAdd 選項）。
- 連線前印出摘要（host/port/user/認證方式/remote_root/capabilities），
  要求明確確認；連到私有網段需要額外的明確確認，metadata IP 永遠拒絕、
  不提供 override。
- 遠端路徑一律用 component-wise walk 逐層 lstat 拒絕 symlink（見
  security/ssh_path_safety.py），不對使用者輸入呼叫 normalize/realpath。
- 讀取的副檔名白名單 + 敏感檔名 denylist，即使副檔名合法，檔名符合
  denylist 的模式（例如 secrets.json）也一律拒絕讀取。
- 讀到的內容若要進報告，一律經過 redact_secrets() 處理；預設報告只放
  path/size/hash 等 metadata，不嵌入檔案原始內容。
- `fetch_url()` 只接受 path-like 輸入（`/a/b.html` 或 `a/b.html`），一律
  拒絕帶 query/fragment/scheme/userinfo 的輸入——SSH 路徑是 SFTP 檔案
  路徑，不是 HTTP URL，把 query 靜默 strip 掉再讀檔會讓行為看起來像成功
  但其實不是使用者以為的目標，因此選擇直接拒絕而非寬容解析。
- `list_urls()` 遞迴掃描 remote_root 下的 `.html`/`.htm` 檔案，有
  `max_depth`/`max_files_scanned`/`max_dirs_scanned` 三重上限（SFTP 每次
  往返都有延遲，不能無上限遞迴），遇到 symlink 目錄或檔案一律跳過
  （不 follow）。
- `get_logs()` 的 log 檔案讀取一律從尾端 tail 讀取（不從頭讀整檔），且
  讀取量固定受位元組數上限限制；`since` 時間篩選參數在 MVP 尚未支援時間
  解析，提供了會直接拋出例外而非靜默忽略造成誤導。
"""

from __future__ import annotations

import fnmatch
import hashlib
from collections import deque
from pathlib import Path
from urllib.parse import urlparse

from seo_advisor.connectors.base import ConnectorCapabilityError, WebsiteConnector
from seo_advisor.models import (
    ConnectorProfile,
    FileRecord,
    LogEntry,
    PageSnapshot,
    SafetyPolicy,
    UrlRecord,
)
from seo_advisor.security.network_policy import is_cloud_metadata_host, is_private_or_blocked_host
from seo_advisor.security.ssh_log_safety import (
    resolve_log_path,
    tail_log_content,
    validate_allowed_log_paths,
)
from seo_advisor.security.ssh_path_safety import (
    RemotePathNotFoundError,
    UnsafeRemotePathError,
    ensure_remote_root_allowed,
    resolve_remote_path,
)

try:
    import paramiko
except ImportError:  # pragma: no cover - 在沒安裝 optional extra 的環境才會走到
    paramiko = None

# 讀取白名單：只涵蓋 SEO 診斷真正需要的靜態資產，刻意不含 .conf/.log/.ini/
# .yml/.env 等常見夾帶憑證/內部設定的格式（NORA×Grok 審查定案收緊後的範圍）。
ALLOWED_READ_EXTENSIONS = frozenset({".html", ".htm", ".xml", ".txt", ".json", ".css"})

# 即使副檔名在白名單內，這些 basename（不分大小寫、不含副檔名比對 stem）
# 一律拒絕讀取，因為這類檔名習慣性地存放憑證/機密設定，寧可誤擋也不誤放。
# 這份清單經過 NORA×Grok 兩輪交叉審查補充；刻意不加入過於寬泛的字詞
# （例如單獨的 "security"，會誤擋合法的 security.txt）。
_DENYLIST_STEMS = frozenset({
    "config", "settings", "secrets", "secret", "credential", "credentials",
    "token", "key", "private", "password", "passwd", "id_rsa", "id_ed25519",
    "id_ecdsa", "id_dsa", "authorized_keys", "known_hosts",
    ".npmrc", ".pypirc", ".netrc",
    "auth", "oauth", "jwt", "session", "cookie", "apikey", "api_key", "api-key",
    "access_key", "access-key", "private_key", "client_secret", "client-secret",
    "serviceaccount", "service_account", "service-account", "firebase-adminsdk",
    "connectionstrings", "connection-strings", "database", "db",
    "local.settings", "composer-auth", "wp-config",
})
_DENYLIST_PATTERNS = (
    ".env*", "*secret*", "*credential*", "*password*", "*token*",
    "service-account*.json", "google-services.json", "firebase*.json",
    "appsettings*.json", "credentials.json", "secrets.json",
)

# 單一檔案讀取大小上限，避免超大檔案吃爆記憶體或造成過長的連線佔用。
_MAX_READ_BYTES = 10 * 1024 * 1024  # 10 MB

# list_urls() 遞迴掃描 remote_root 的三重上限：SFTP 每次 listdir_attr()
# 往返都有網路延遲，不能無上限遞迴，避免對遠端伺服器造成過度負擔或讓單次
# 掃描耗時失控。
_MAX_SCAN_DEPTH = 5
_MAX_FILES_SCANNED = 2000
_MAX_DIRS_SCANNED = 500

# 掃描時跳過的目錄名稱（版控/依賴套件/暫存/備份），避免把這些目錄內的
# .html 檔案誤判為真實網站頁面。
_SKIPPED_DIR_NAMES = frozenset({
    ".git", ".svn", ".seo-advisor", "node_modules", "vendor",
    "dist", "cache", "tmp", "backup",
})

# get_logs() 的 tail 讀取上限：預設值與硬上限，即使呼叫端要求更大的
# tail 範圍也不能超過硬上限。
_DEFAULT_LOG_TAIL_BYTES = 256 * 1024  # 256 KB
_MAX_LOG_TAIL_BYTES = 2 * 1024 * 1024  # 2 MB

# 過寬 root 以外，還要對常見「其實是系統/共用主機根目錄」的情況多一層警告；
# 這裡沿用 security/ssh_path_safety.py 的 ensure_remote_root_allowed()。


class SSHConnectorError(RuntimeError):
    """SSH 連線/認證相關的錯誤（非路徑安全類，那些見 UnsafeRemotePathError）。"""


class UnknownHostKeyError(SSHConnectorError):
    """目標主機不在使用者的 known_hosts 內，且未提供的信任来源時拋出。"""


def _reject_unsafe_fetch_url(url: str) -> str | None:
    """檢查 fetch_url() 收到的 url 是否為合法的 path-like 輸入。

    SSH 路徑是 SFTP 檔案路徑，不是 HTTP URL：只接受 `/a/b.html` 或
    `a/b.html` 這種純路徑，明確拒絕 query/fragment/scheme/userinfo。
    刻意不用 urlparse 後只取 `.path` 再讀檔——那等於靜默丟棄 query，
    行為看起來像成功但其實不是使用者以為的目標，比直接拒絕更危險。

    回傳 None 代表通過檢查；否則回傳給使用者看的錯誤說明文字。
    """
    if "?" in url or "#" in url:
        return (
            f"{url!r} 含有 query string 或 fragment（'?'/'#'），"
            "SSHConnector 的 fetch_url() 只接受純路徑（不支援 HTTP 查詢字串語意），已拒絕。"
        )

    parsed = urlparse(url)
    if parsed.scheme:
        return f"{url!r} 含有 scheme（{parsed.scheme}:），SSHConnector 只接受相對路徑，已拒絕。"
    if parsed.username or parsed.password:
        return f"{url!r} 含有帳號密碼資訊，已拒絕。"

    return None


def _is_read_target_allowed(path: str) -> bool:
    """檢查路徑是否符合讀取白名單/denylist。副檔名需在允許清單內，且
    basename 的 stem 不得落在敏感檔名 denylist 或 pattern denylist 裡。
    """
    basename = path.rsplit("/", 1)[-1].lower()
    stem = basename.split(".", 1)[0] if "." in basename else basename

    if stem in _DENYLIST_STEMS:
        return False
    if any(fnmatch.fnmatch(basename, pattern) for pattern in _DENYLIST_PATTERNS):
        return False

    suffix = "." + basename.rsplit(".", 1)[-1] if "." in basename else ""
    return suffix in ALLOWED_READ_EXTENSIONS


class SSHConnector(WebsiteConnector):
    """透過 SFTP 唯讀存取遠端伺服器的網站檔案。capabilities() 只回報
    {"read_files"}；write_file()/run_command() 完全不 override。
    """

    def __init__(
        self,
        host: str,
        *,
        user: str,
        remote_root: str,
        port: int = 22,
        key_path: str | None = None,
        known_hosts_path: str | None = None,
        policy: SafetyPolicy | None = None,
        confirm_connect: str | None = None,
        allow_private_network: bool = False,
        timeout_seconds: float = 15.0,
        allowed_log_paths: dict[str, str] | None = None,
    ) -> None:
        self.policy = policy or SafetyPolicy(allowed_capabilities={"read_files", "read_urls"})
        self._host = host
        self._user = user
        self._port = port
        self._remote_root_input = remote_root

        # 語法層驗證放在任何網路操作之前完成（跟確認字串驗證同樣的原則：
        # 不需要遠端連線就能判斷合法性的檢查，應該儘早失敗）。
        self._allowed_log_paths = (
            validate_allowed_log_paths(allowed_log_paths) if allowed_log_paths else {}
        )

        # 確認字串驗證必須在任何網路操作（含 DNS 解析、TCP 連線）之前完成
        # ——即使 DNS 解析/socket 建立本身看起來「無害」，對目標主機發送
        # 任何封包都是一次網路接觸，在使用者還沒明確確認授權之前就這麼做
        # 不符合「先同意才動作」的原則（Grok 在複審時抓到這個順序問題：
        # 原本的實作是先完成 DNS 解析+TCP 連線，才驗證確認字串）。
        # 這個檢查刻意放在 paramiko 是否安裝的檢查之前：即使呼叫端根本沒
        # 安裝 optional extra，這一層純邏輯驗證也該先執行完畢——paramiko
        # 只有在真的要建立 SSH session 時才需要用到（見 _connect()）。
        expected_confirm = self.build_connect_confirmation()
        if confirm_connect is None or confirm_connect.strip().upper() != expected_confirm.upper():
            raise SSHConnectorError(
                f"連線前需要明確確認。請提供 confirm_connect={expected_confirm!r}，"
                "確認你有權對這個主機/帳號執行 SEO 診斷讀取。"
            )

        # 連線目標檢查與 TCP 連線建立合併為一個原子操作，避免 DNS
        # rebinding TOCTOU：如果「檢查網段」跟「實際連線」是兩次獨立的
        # DNS 解析，攻擊者可以用短 TTL 的 DNS 記錄，讓檢查時解析到安全的
        # 公開 IP、連線時已經改指向 metadata/內網 IP。做法是只解析一次
        # host，對解析出的每個 IP 做網段檢查，全部通過後直接用該 IP
        # 建立 TCP socket，再把這個已連線的 socket 交給 paramiko（見
        # _connect 的 sock 參數），paramiko 仍用原始 hostname 做 host key
        # 查找，不影響 known_hosts 驗證。
        verified_sock = self._resolve_and_verify_host(
            host, port, allow_private_network=allow_private_network, timeout_seconds=timeout_seconds
        )

        auth_method = self._connect(
            sock=verified_sock, key_path=key_path, known_hosts_path=known_hosts_path,
            timeout_seconds=timeout_seconds,
        )
        self._auth_method = auth_method

        self._sftp = self._client.open_sftp()
        remote_root_real = self._sftp.normalize(remote_root)
        ensure_remote_root_allowed(remote_root_real)
        self._remote_root_real = remote_root_real

    # --- 連線與認證 ---

    def _resolve_and_verify_host(
        self, host: str, port: int, *, allow_private_network: bool, timeout_seconds: float
    ):
        """只對 host 做一次 DNS 解析，對解析出的每個候選 IP 做網段檢查，
        全部通過後用第一個可連線成功的 IP 建立 TCP socket 並回傳。

        刻意不分成「先查網段」「再讓 paramiko 自己連線重新查一次網段」兩步
        ——那樣兩次解析之間就是 TOCTOU 的時間窗口。這裡把「檢查」跟「連線」
        用同一次解析結果完成，攻擊者無法在檢查通過之後才讓 DNS 改指向別處。
        """
        import socket as socket_module

        try:
            infos = socket_module.getaddrinfo(host, port, type=socket_module.SOCK_STREAM)
        except socket_module.gaierror as exc:
            raise SSHConnectorError(f"無法解析主機名稱 {host!r}：{exc}") from exc

        if not infos:
            raise SSHConnectorError(f"無法解析主機名稱 {host!r}：DNS 查詢沒有回傳任何位址。")

        for family, socktype, proto, _, sockaddr in infos:
            candidate_ip = sockaddr[0]
            self._ensure_ip_allowed(candidate_ip, allow_private_network=allow_private_network)

        last_error: Exception | None = None
        for family, socktype, proto, _, sockaddr in infos:
            sock = socket_module.socket(family, socktype, proto)
            sock.settimeout(timeout_seconds)
            try:
                sock.connect(sockaddr)
                return sock
            except OSError as exc:
                sock.close()
                last_error = exc
                continue

        raise SSHConnectorError(f"無法連線到 {host!r} 的任何已解析位址：{last_error}")

    def _ensure_ip_allowed(self, ip_str: str, *, allow_private_network: bool) -> None:
        if is_cloud_metadata_host(ip_str):
            raise SSHConnectorError(
                f"目標 {self._host!r}（解析為 {ip_str}）是雲端 metadata 位址，"
                "SSHConnector 永遠拒絕連線到這類位址，不提供任何開關可以覆寫。"
            )

        if not allow_private_network and is_private_or_blocked_host(ip_str):
            raise SSHConnectorError(
                f"目標主機 {self._host!r}（解析為 {ip_str}）指向私有網段/本機。"
                "若你確實要連線到自己的內網伺服器，"
                "請明確傳入 allow_private_network=True 並提供對應的確認字串。"
            )

    def build_connect_confirmation(self) -> str:
        return f"CONNECT {self._host}:{self._port}"

    def _connect(self, *, sock, key_path: str | None, known_hosts_path: str | None,
                 timeout_seconds: float) -> str:
        if paramiko is None:
            sock.close()
            raise SSHConnectorError(
                "SSHConnector 需要安裝 paramiko，請執行："
                "pip install \"open-seo-advisor-skill[ssh]\""
            )

        client = paramiko.SSHClient()

        host_keys_path = known_hosts_path or str(Path.home() / ".ssh" / "known_hosts")
        try:
            client.load_host_keys(host_keys_path)
        except FileNotFoundError as exc:
            raise SSHConnectorError(
                f"找不到 known_hosts 檔案：{host_keys_path}。"
                "SSHConnector 要求主機金鑰已經在你本機的 known_hosts 中（例如先手動執行過一次 "
                "`ssh user@host` 建立信任關係），不提供自動信任未知主機的選項。"
            ) from exc

        # 明確拒絕任何形式的「自動信任未知主機」：不設定 missing_host_key_policy
        # 時 paramiko 預設就是拒絕未知主機金鑰（RejectPolicy），這裡保留預設值、
        # 刻意不呼叫 set_missing_host_key_policy(AutoAddPolicy())。

        connect_kwargs: dict = {
            "hostname": self._host,
            "port": self._port,
            "username": self._user,
            "timeout": timeout_seconds,
            "sock": sock,
            "allow_agent": key_path is None,
            "look_for_keys": key_path is None,
        }
        if key_path:
            connect_kwargs["key_filename"] = key_path
            auth_method = "key_path"
        else:
            auth_method = "agent"

        try:
            client.connect(**connect_kwargs)
        except paramiko.ssh_exception.SSHException as exc:
            # 例外訊息可能夾帶主機金鑰細節，不含憑證本身，但仍統一走
            # redact_secrets() 由上層 CLI/errors.py 處理，這裡不重複處理。
            raise SSHConnectorError(f"SSH 連線失敗：{exc}") from exc

        self._client = client
        return auth_method

    # --- WebsiteConnector 抽象方法 ---

    def id(self) -> str:
        return f"ssh:{self._user}@{self._host}:{self._port}"

    def capabilities(self) -> set[str]:
        caps = {"read_files", "read_urls"}
        if self._allowed_log_paths:
            caps.add("read_logs")
        return caps

    def probe(self) -> ConnectorProfile:
        notes = [
            f"已連線：{self._user}@{self._host}:{self._port}（認證方式：{self._auth_method}）",
            f"授權範圍（remote_root）：{self._remote_root_real}",
        ]
        if self._allowed_log_paths:
            notes.append(f"已設定 log 白名單：{sorted(self._allowed_log_paths.keys())}")
        return ConnectorProfile(source_type="ssh", detected_stack=None, notes=notes)

    def list_urls(self, seed: str, limit: int) -> list[UrlRecord]:
        """遞迴掃描 remote_root 下的 .html/.htm 檔案，包裝成 URL 爬取介面。

        受 max_depth/max_files_scanned/max_dirs_scanned 三重上限約束——SFTP
        每次 listdir_attr() 往返都有網路延遲，不能無上限遞迴；遇到 symlink
        目錄或檔案一律跳過（list_files() 已經先過濾掉 symlink），版控/依賴
        套件/暫存目錄也一律跳過，避免誤判為真實網站頁面。
        """
        records: list[UrlRecord] = []
        dirs_scanned = 0
        # (相對路徑, 深度) 的 BFS 佇列，用 deque 讓 popleft() 是 O(1)
        # （list.pop(0) 是 O(n)，雖有 _MAX_DIRS_SCANNED 上限但仍值得用
        # 正確的資料結構）。
        queue: deque[tuple[str, int]] = deque([("", 0)])

        while queue and len(records) < limit:
            rel_dir, depth = queue.popleft()
            if dirs_scanned >= _MAX_DIRS_SCANNED:
                break
            dirs_scanned += 1

            try:
                entries = self.list_files(rel_dir)
            except (RemotePathNotFoundError, UnsafeRemotePathError):
                continue

            for entry in entries:
                if len(records) >= limit:
                    break
                basename = entry.path.rsplit("/", 1)[-1]
                if entry.is_dir:
                    if basename in _SKIPPED_DIR_NAMES:
                        continue
                    if depth + 1 <= _MAX_SCAN_DEPTH:
                        queue.append((entry.path, depth + 1))
                    continue

                if entry.path.lower().endswith((".html", ".htm")):
                    records.append(
                        UrlRecord(url=f"/{entry.path}", source="crawl", discovered_depth=depth)
                    )
                    if len(records) >= _MAX_FILES_SCANNED:
                        break

        return records[:limit]

    def fetch_url(self, url: str, *, render: bool = False, fetched_at: str = "") -> PageSnapshot:
        if render:
            raise NotImplementedError("SSHConnector 不支援 render=True（無 headless browser）。")

        rejection = _reject_unsafe_fetch_url(url)
        if rejection is not None:
            return PageSnapshot(
                url=url, status_code=0, final_url=url, headers={}, html="", fetched_at=fetched_at,
                fetch_error_type="unsafe_remote_path", fetch_error_message=rejection,
            )

        rel_path = url.lstrip("/")
        try:
            content = self.read_file(rel_path)
        except (RemotePathNotFoundError, FileNotFoundError):
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

    # --- read_files capability ---

    def list_files(self, path: str) -> list[FileRecord]:
        self.policy.require_capability("read_files", connector_id=self.id())

        target = resolve_remote_path(self._sftp, self._remote_root_real, path) if path else None
        remote_dir = self._remote_root_real if target is None else (
            self._remote_root_real.rstrip("/") + "/" + target.path
        )

        records: list[FileRecord] = []
        for attr in self._sftp.listdir_attr(remote_dir):
            import stat as _stat
            is_dir = _stat.S_ISDIR(attr.st_mode)
            is_link = _stat.S_ISLNK(attr.st_mode)
            if is_link:
                # 列出但不 follow：呼叫端若嘗試 read_file 這個路徑，
                # resolve_remote_path 會在解析階段再次拒絕。
                continue
            rel_prefix = f"{target.path}/" if target and target.path else ""
            records.append(
                FileRecord(
                    path=f"{rel_prefix}{attr.filename}",
                    size_bytes=attr.st_size or 0,
                    is_dir=is_dir,
                )
            )
        return records

    def read_file(self, path: str) -> bytes:
        self.policy.require_capability("read_files", connector_id=self.id())

        if not _is_read_target_allowed(path):
            raise UnsafeRemotePathError(
                f"{path!r} 不在允許讀取的副檔名範圍內，或檔名符合敏感檔名 denylist，已拒絕讀取。"
            )

        resolved = resolve_remote_path(self._sftp, self._remote_root_real, path)
        if resolved.is_dir:
            raise UnsafeRemotePathError(f"{path!r} 是目錄，不是檔案，無法讀取。")
        if resolved.size > _MAX_READ_BYTES:
            raise SSHConnectorError(
                f"{path!r} 大小（{resolved.size} bytes）超過上限（{_MAX_READ_BYTES} bytes），拒絕讀取。"
            )

        remote_path = self._remote_root_real.rstrip("/") + "/" + resolved.path
        with self._sftp.open(remote_path, "rb") as f:
            content = f.read(_MAX_READ_BYTES + 1)
        if len(content) > _MAX_READ_BYTES:
            raise SSHConnectorError(f"{path!r} 讀取內容超過大小上限，已中止讀取。")
        return content

    # --- read_logs capability（選配，只有提供 allowed_log_paths 才可用）---

    def get_logs(self, log_type: str, since: str | None = None) -> list[LogEntry]:
        """從 `allowed_log_paths` 白名單指定的 log 檔案尾端讀取內容。

        MVP 不解析各種 log format 的時間戳記（nginx/apache 格式差異很大，
        硬解析容易誤判），因此：
        - `since` 若提供非 None 值，直接拋出例外，而不是靜默忽略——忽略
          會讓使用者誤以為真的做了時間篩選，篩選結果卻是全部內容，這種
          「看似成功但語意不對」的行為比明確拒絕更危險。
        - 每一行對應一個 `LogEntry`，`timestamp` 固定為空字串（沒有可靠
          解析出時間戳記），`source` 記錄 log_type，`message` 是該行內容
          （已套用 redact_secrets 與 log 專用的 query/auth 參數遮蔽）。

        讀取一律從檔案尾端 tail（不從頭讀整檔），受位元組數上限約束；
        檔案在讀取期間持續被寫入/rotate 屬於已知的正確性層面殘餘風險
        （見 security/ssh_log_safety.py::tail_log_content 的說明），
        不是安全層面的 jail escape。

        未提供 allowed_log_paths 時直接拋出 ConnectorCapabilityError
        （與 capabilities() 不含 "read_logs" 一致），而不是先撞到
        SafetyPolicy 的 PermissionError——這裡的根本原因是「這個 connector
        實例根本沒有這個能力」，不是「policy 沒開放這個能力」，錯誤訊息
        應該讓使用者一眼看出差異。
        """
        if not self._allowed_log_paths:
            raise ConnectorCapabilityError(
                f"{self.id()} 未設定 allowed_log_paths，get_logs() 無法使用。"
                "請在建立 SSHConnector 時明確傳入 allowed_log_paths 白名單。"
            )

        self.policy.require_capability("read_logs", connector_id=self.id())

        if log_type not in self._allowed_log_paths:
            raise SSHConnectorError(
                f"log_type {log_type!r} 不在允許的白名單內，可用的 log_type："
                f"{sorted(self._allowed_log_paths.keys())}"
            )
        if since is not None:
            raise SSHConnectorError(
                "get_logs() 的 since 時間篩選在目前版本尚未支援（不同 log format 的"
                "時間戳記解析差異很大，尚未實作），請省略此參數以讀取檔案尾端內容。"
            )

        log_path = self._allowed_log_paths[log_type]
        resolved_path = resolve_log_path(self._sftp, log_path)
        raw_content = tail_log_content(
            self._sftp, resolved_path, max_tail_bytes=_DEFAULT_LOG_TAIL_BYTES
        )

        # 延後匯入：errors.py 匯入 scan_runner（取得 SiteUnreachableError），
        # 而 scan_runner 需要匯入 SSHConnector 才能建立 SSH 來源的掃描，
        # 在模組頂層互相匯入會形成循環 import，因此改在使用時才匯入。
        from seo_advisor.errors import redact_secrets

        text = raw_content.decode("utf-8", errors="replace")
        entries: list[LogEntry] = []
        for line in text.splitlines():
            if not line:
                continue
            entries.append(LogEntry(timestamp="", source=log_type, message=redact_secrets(line)))
        return entries

    def close(self) -> None:
        sftp = getattr(self, "_sftp", None)
        if sftp is not None:
            sftp.close()
        client = getattr(self, "_client", None)
        if client is not None:
            client.close()


def hash_content(content: bytes) -> str:
    """供呼叫端在報告裡放檔案內容的摘要 metadata 而非原文使用。"""
    return hashlib.sha256(content).hexdigest()
