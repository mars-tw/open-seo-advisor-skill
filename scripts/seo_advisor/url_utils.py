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

    hostname = parsed.hostname or ""
    if not _DOMAIN_PATTERN.match(hostname) and hostname != "localhost":
        raise InvalidUrlError(
            f"「{raw}」看起來不是一個有效的網址。請確認網域名稱是否有打錯字，"
            f"例如：example.com 或 https://example.com"
        )

    return text
