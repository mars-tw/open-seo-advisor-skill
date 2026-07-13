"""遠端檔案讀取的副檔名白名單 + 敏感檔名 denylist，供 SSHConnector 與
CPanelConnector 共用（原本各自在 SSHConnector 內定義，抽成共用模組避免
未來新增遠端 connector 時兩份定義各自漂移）。

背景：這份白名單/denylist 經過 NORA×Grok 交叉審查定案（SSHConnector 的
設計辯論），只涵蓋 SEO 診斷真正需要的靜態資產，刻意不含 .conf/.log/.ini/
.yml/.env 等常見夾帶憑證/內部設定的格式；即使副檔名合法，敏感 basename
也一律拒絕，寧可誤擋也不誤放。
"""

from __future__ import annotations

import fnmatch

# 讀取白名單：只涵蓋 SEO 診斷真正需要的靜態資產。
ALLOWED_READ_EXTENSIONS = frozenset({".html", ".htm", ".xml", ".txt", ".json", ".css"})

# 即使副檔名在白名單內，這些 basename（不分大小寫、不含副檔名比對 stem）
# 一律拒絕讀取，因為這類檔名習慣性地存放憑證/機密設定。
DENYLIST_STEMS = frozenset({
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
DENYLIST_PATTERNS = (
    ".env*", "*secret*", "*credential*", "*password*", "*token*",
    "service-account*.json", "google-services.json", "firebase*.json",
    "appsettings*.json", "credentials.json", "secrets.json",
)


def is_read_target_allowed(path: str) -> bool:
    """檢查路徑是否符合讀取白名單/denylist。副檔名需在允許清單內，且
    basename 的 stem 不得落在敏感檔名 denylist 或 pattern denylist 裡。
    """
    basename = path.rsplit("/", 1)[-1].lower()
    stem = basename.split(".", 1)[0] if "." in basename else basename

    if stem in DENYLIST_STEMS:
        return False
    if any(fnmatch.fnmatch(basename, pattern) for pattern in DENYLIST_PATTERNS):
        return False

    suffix = "." + basename.rsplit(".", 1)[-1] if "." in basename else ""
    return suffix in ALLOWED_READ_EXTENSIONS
