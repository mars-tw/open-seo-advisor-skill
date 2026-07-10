"""WordPressAPIConnector 專用的 URL scope 驗證。

背景：WordPress REST API 回傳的 `posts[].link`/`pages[].link` 欄位必須被視為
attacker-controlled 輸入（資料庫被注入、惡意外掛都可能竄改這個欄位），不能直接
交給 fetch 邏輯發送網路請求，否則等於讓「使用者信任的目標網站」的資料變成可以
指向任意主機（包含雲端 metadata IP、內網服務、完全無關的第三方網站）的跳板。

這是 NORA×Grok 雙模型交叉辯論（WordPressAPIConnector v0.2.4 設計辯論）定案的
scope 演算法，核心規則：
1. 只接受 http/https，拒絕 userinfo、javascript:/data:/file: 等 scheme。
2. host 必須精確符合，或符合單層 www<->apex pair（不剝除多層、不做後綴比對）。
3. scheme 必須與初始化時鎖定的 authorized_scheme 相同（不允許 https 站被導去抓
   http 版本，避免明文降級）。
4. port 正規化後必須相同。
5. path 必須落在 authorized_path_prefix 之內，用 URL-decode 後的 segment 邊界
   比對，不能用裸字串 startswith（否則 "/blog" 會誤放行 "/blogevil/..."）。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote, urlparse

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_DEFAULT_PORTS = {"http": 80, "https": 443}


class InvalidWordPressUrlError(ValueError):
    """URL 本身就不合法（scheme 不對、含 userinfo 等），連 scope 比對都不用做。"""


@dataclass(frozen=True)
class WordPressScope:
    """建構子時鎖定的授權範圍，之後所有 scope 檢查都只跟這個做比較。

    不會因為任何 REST 回傳的 link 或 redirect 目標而動態擴大——這是與
    HTTPConnector._register_final_host（爬蟲遇到 redirect 會把新 host 加入
    允許集合）刻意不同的設計：WP connector 的授權範圍在使用者輸入 base_url
    的當下就完全固定，REST 回傳的資料不具備擴大這個範圍的權力。
    """

    scheme: str
    host: str
    port: int
    path_prefix: str

    @classmethod
    def from_base_url(cls, base_url: str) -> "WordPressScope":
        parsed = urlparse(base_url)
        if parsed.scheme not in _ALLOWED_SCHEMES or not parsed.hostname:
            raise InvalidWordPressUrlError(
                f"base_url 必須是完整的 http(s) 網址，收到：{base_url!r}"
            )
        if parsed.username or parsed.password:
            raise InvalidWordPressUrlError(
                "base_url 不應包含帳號密碼（例如 https://user:pass@example.com），"
                "請在獨立參數中提供 Application Password，不要夾帶在網址裡。"
            )
        host = _normalize_host_exact(parsed.hostname)
        if not host:
            raise InvalidWordPressUrlError("base_url 的主機名稱不能是空白。")
        port = parsed.port or _DEFAULT_PORTS[parsed.scheme]
        prefix = _normalize_path_prefix(parsed.path)
        return cls(scheme=parsed.scheme, host=host, port=port, path_prefix=prefix)


def _normalize_host_exact(hostname: str) -> str:
    """僅做 lowercase + 去掉結尾的點，不剝除 www——www/apex 的等價關係由
    `_is_www_apex_pair` 獨立判斷，兩種正規化目的不同不能混用同一個函式：
    這裡回傳的值是「這個字面 host 到底是什麼」，不是「屬於哪個站」。
    """
    host = hostname.lower().strip()
    if host.endswith("."):
        host = host[:-1]
    try:
        host = host.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        pass
    return host


def _is_www_apex_pair(candidate_host: str, authorized_host: str) -> bool:
    """只允許「單層 www 前綴」的等價，不做遞迴剝除、不做網域後綴比對。

    刻意排除的情境：
    - "www.www.example.com" 不會被誤判等於 "example.com"（不遞迴剝除）。
    - "notexample.com" 不會因為後綴含 "example.com" 就被誤判等於它
      （這裡本來就是做 exact 比較，不是 endswith）。
    """
    if candidate_host == authorized_host:
        return True
    return (
        candidate_host == "www." + authorized_host
        or authorized_host == "www." + candidate_host
    )


def _normalize_path_prefix(raw_path: str) -> str:
    """把 base_url 的 path 正規化成用來比對子路徑的前綴：空字串或 "/" 代表
    整站都在授權範圍（只受 host/scheme/port 約束），否則回傳去掉結尾斜線、
    以 "/" 開頭的字串（例如 "/blog"）。
    """
    path = raw_path or "/"
    if path in ("", "/"):
        return ""
    return path.rstrip("/")


def _path_under_prefix(path: str, prefix: str) -> bool:
    """用 URL-decode 之後的 segment 邊界比對，取代危險的裸字串
    `path.startswith(prefix)`——那種寫法會讓 prefix="/blog" 誤放行
    "/blogevil/..." 或 "/blog-backup/..."。

    decode 一次後以 "/" 切成 segment，任何 segment 是 ".." 就整條路徑拒絕
    （不嘗試「消解後再比較」，避免消解邏輯本身出現繞過空間）；"." segment
    直接忽略（視為 no-op，不影響邊界判斷）。
    """
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


def is_url_in_scope(url: str, scope: WordPressScope) -> bool:
    """判斷一個 URL（通常來自 REST API 回傳的 link 欄位，必須視為
    attacker-controlled）是否落在這個 WordPressAPIConnector 實例的授權範圍內。

    任何一項不符合就整體回傳 False，呼叫端應該把這個 URL 丟棄並記錄到
    skipped/notes，絕不能讓它進入 crawler 或 fetch_url()。
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
