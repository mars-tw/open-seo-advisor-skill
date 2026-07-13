"""IndexNow 提交前的 URL 語法/scope 驗證。

背景：要提交給 IndexNow API 的 URL 清單是使用者輸入的（通常來自
`--urls-file` 或 Engineer Mode 報告），必須驗證這些 URL 確實屬於這次
提交鎖定的網站範圍，避免使用者不小心把不相關/第三方的網址混進提交清單
（IndexNow 協定本身要求提交的 URL 必須與 keyLocation 同網域，即使協定
本身會擋，這裡在送出前先做一層語法驗證能更早給出清楚的錯誤訊息，也
避免浪費 API 配額在注定失敗的請求上）。

scope 判斷邏輯與 security/wp_url_scope.py 的核心規則一致（host 精確符合
或單層 www/apex pair、path segment 邊界比對，不用裸字串 startswith），
但這裡刻意獨立實作而非直接 import 那個模組——wp_url_scope.py 是
WordPressAPIConnector 經 NORA×Grok 三輪辯論定案的核心安全模組，不希望
IndexNow 這個功能牽動它的穩定性；IndexNow 額外允許 URL 帶 query string
（協定官方範例本身就包含帶 query 的 URL）。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote, urlparse

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_DEFAULT_PORTS = {"http": 80, "https": 443}


class InvalidIndexNowScopeError(ValueError):
    """site/keyLocation 本身格式不合法時拋出。"""


@dataclass(frozen=True)
class IndexNowScope:
    """建構子時鎖定的授權範圍：由 keyLocation 決定（協定規定提交的 URL
    必須落在 keyLocation 所在目錄之下，若 key 檔案不在網站根目錄，等於
    宣告只對該子目錄下的 URL 有效）。
    """

    scheme: str
    host: str
    port: int
    path_prefix: str

    @classmethod
    def from_key_location(cls, key_location: str) -> "IndexNowScope":
        parsed = urlparse(key_location)
        if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
            raise InvalidIndexNowScopeError(f"keyLocation 必須是完整的 http(s) 網址，收到：{key_location!r}")
        if parsed.username or parsed.password:
            raise InvalidIndexNowScopeError("keyLocation 不應包含帳號密碼資訊。")
        host = _normalize_host_exact(parsed.hostname)
        if not host:
            raise InvalidIndexNowScopeError("keyLocation 的主機名稱不能是空白。")
        port = parsed.port or _DEFAULT_PORTS[parsed.scheme]
        # key 檔案本身所在的目錄才是 scope 的 path_prefix（key 檔案的
        # basename 不算在授權目錄範圍內，只有它所在的目錄）。
        prefix = _normalize_path_prefix(parsed.path.rsplit("/", 1)[0] if "/" in parsed.path else "")
        return cls(scheme=parsed.scheme, host=host, port=port, path_prefix=prefix)


def _normalize_host_exact(hostname: str) -> str:
    host = hostname.lower().strip()
    if host.endswith("."):
        host = host[:-1]
    try:
        host = host.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        pass
    return host


def _is_www_apex_pair(candidate_host: str, authorized_host: str) -> bool:
    if candidate_host == authorized_host:
        return True
    return candidate_host == "www." + authorized_host or authorized_host == "www." + candidate_host


def _normalize_path_prefix(raw_path: str) -> str:
    path = raw_path or "/"
    if path in ("", "/"):
        return ""
    return path.rstrip("/")


def _path_under_prefix(path: str, prefix: str) -> bool:
    try:
        decoded = unquote(path, errors="strict")
    except UnicodeDecodeError:
        return False
    if "\x00" in decoded:
        return False

    segments = [seg for seg in decoded.split("/") if seg != "."]
    if any(seg == ".." for seg in segments):
        return False

    if prefix == "":
        return True
    if decoded == prefix or decoded == prefix + "/":
        return True
    return decoded.startswith(prefix + "/")


def is_url_in_scope(url: str, scope: IndexNowScope) -> bool:
    """判斷提交的 URL 是否落在 keyLocation 決定的授權範圍內。與
    wp_url_scope.is_url_in_scope 的差異：這裡不因為 URL 帶 query string
    而拒絕（IndexNow 協定官方範例本身就包含帶 query 的 URL），fragment
    仍然拒絕（fragment 是純前端錨點，不該出現在要求搜尋引擎重新索引的
    URL 裡，官方文件也沒有納入 fragment 的討論）。
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme not in _ALLOWED_SCHEMES:
        return False
    if not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    if parsed.fragment:
        return False
    if parsed.scheme != scope.scheme:
        return False

    candidate_host = _normalize_host_exact(parsed.hostname)
    if not _is_www_apex_pair(candidate_host, scope.host):
        return False

    candidate_port = parsed.port or _DEFAULT_PORTS[parsed.scheme]
    if candidate_port != scope.port:
        return False

    if not _path_under_prefix(parsed.path or "/", scope.path_prefix):
        return False

    return True
