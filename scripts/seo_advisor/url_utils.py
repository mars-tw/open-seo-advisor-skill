"""URL 正規化工具：讓新手不需要記得要打 https:// 才能開始掃描。

規則：
1. 使用者輸入 "example.com" 或 "www.example.com" 時，自動補上 https://。
2. 優先嘗試 https，只有在明確需要時才退回 http（由呼叫端決定是否重試）。
3. 明顯不是網址格式時，回傳清楚的錯誤，而不是讓後續連線失敗才報錯。
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

_DOMAIN_PATTERN = re.compile(
    r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)


class InvalidUrlError(ValueError):
    """使用者輸入的內容看起來不像網址時拋出，附帶人話說明。"""


def normalize_url(raw: str) -> str:
    """把使用者輸入的字串正規化成完整 URL（預設補 https://）。

    範例：
        "example.com"          -> "https://example.com"
        "www.example.com"      -> "https://www.example.com"
        "http://example.com"   -> "http://example.com"（保留使用者指定的 scheme）
        "not a url"            -> 拋出 InvalidUrlError
    """
    text = raw.strip()
    if not text:
        raise InvalidUrlError("網址不能是空白，請輸入例如 example.com 這樣的網址。")

    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", text):
        text = f"https://{text}"

    parsed = urlparse(text)
    if not parsed.netloc:
        raise InvalidUrlError(
            f"「{raw}」看起來不是一個有效的網址。請輸入完整網址，"
            f"例如：example.com 或 https://example.com"
        )

    if parsed.username or parsed.password:
        raise InvalidUrlError(
            "網址中不應包含帳號密碼（例如 https://user:pass@example.com），"
            "這類憑證可能會被意外記錄到報告或日誌中造成外洩。"
            "請直接輸入網址本身，不要在網址中夾帶帳密。"
        )

    hostname = parsed.hostname or ""
    if not _DOMAIN_PATTERN.match(hostname) and hostname != "localhost":
        raise InvalidUrlError(
            f"「{raw}」看起來不是一個有效的網址。請確認網域名稱是否有打錯字，"
            f"例如：example.com 或 https://example.com"
        )

    return text


def looks_like_url(raw: str) -> bool:
    """判斷使用者輸入比較像「網址」還是「一句目標描述」。

    給 autopilot 之類需要區分兩者的地方用：新手常直接打 `example.com`（沒有
    https://、也沒有空白），這種要能被當成網址；而「幫我規劃成長方案」這種
    含空白的自然語言則不是網址。判斷方式是嘗試 normalize_url，成功即視為網址。
    """
    text = raw.strip()
    if not text or " " in text or "　" in text:
        return False
    try:
        normalize_url(text)
        return True
    except InvalidUrlError:
        return False


def normalize_host(host: str) -> str:
    """正規化主機名稱以比較是否「實質同站」：lowercase、去掉單層 www.、
    去掉預設 port。這樣 www.x.com 與 x.com 會被視為同站，避免把最常見的
    合法 canonicalization（www↔apex）誤判成跨網域/外部連結。

    這是連接爬取層（connectors/http.py 的爬取範圍判斷、crawler.py 的同站
    連結判斷）與分析層（analyzers/technical.py 的 canonical 跨網域檢查）
    共用的正規化邏輯，刻意放在最底層、不依賴任何 seo_advisor 內部模組的
    url_utils，避免爬取層依賴分析層造成不當耦合。
    """
    host = host.lower().strip()
    # 去掉 :80 / :443 等 port（保留非預設 port 以免混淆不同服務）
    if ":" in host:
        name, _, port = host.rpartition(":")
        if port in ("80", "443"):
            host = name
    if host.startswith("www."):
        host = host[4:]
    return host
