"""偵測 HTML 檔案的字元編碼，避免非 UTF-8 網站（Big5、Shift_JIS、GBK 等）被
一律用 UTF-8 + errors="replace" 讀取，導致中日韓文字亂碼，進而讓 title/H1/meta
等分析誤判（例如把亂碼判斷成缺少內容、或重複標題誤判增加）。

偵測順序（由高到低優先）：
1. BOM（UTF-8/UTF-16/UTF-32 的位元組順序記號）
2. HTML 內的 `<meta charset="...">` 或
   `<meta http-equiv="Content-Type" content="...; charset=...">` 宣告
3. 都沒有時，fallback 為 UTF-8（errors="replace"，不讓讀取本身失敗）

不使用 chardet/charset-normalizer 之類的機率性偵測套件，因為 HTML 檔案通常
會自行宣告編碼，用宣告值已能涵蓋絕大多數情況，且能維持零額外相依。
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_CONTENT_CHARSET = re.compile(r'(?:^|;)\s*charset\s*=\s*["\']?([a-z0-9_.-]+)', re.I)


class _EncodingDeclaration(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.encoding = None
        self.inert = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"template", "noscript"}:
            self.inert += 1
        if self.inert or self.encoding or tag != "meta":
            return
        values = {key: (value or "").strip() for key, value in attrs}
        label = values.get("charset")
        if not label and values.get("http-equiv", "").casefold() == "content-type":
            match = _CONTENT_CHARSET.search(values.get("content", ""))
            if match:
                label = match.group(1)
        if label and re.fullmatch(r"[a-zA-Z0-9_.-]+", label):
            self.encoding = label.casefold()

    def handle_endtag(self, tag):
        if tag in {"template", "noscript"} and self.inert:
            self.inert -= 1


_BOM_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
]


def declared_html_encoding(raw_bytes: bytes) -> str | None:
    """Read a BOM or active HTML declaration without decoding the document body."""
    for signature, encoding in _BOM_SIGNATURES:
        if raw_bytes.startswith(signature):
            return encoding

    parser = _EncodingDeclaration()
    try:
        parser.feed(raw_bytes[:4096].decode("latin-1"))
    except (AssertionError, ValueError):
        pass  # A malformed or incomplete declaration is not an encoding hint.
    return parser.encoding


def detect_html_encoding(raw_bytes: bytes) -> str:
    return declared_html_encoding(raw_bytes) or "utf-8"


def decode_html_bytes(raw_bytes: bytes) -> str:
    """依偵測到的編碼解碼 HTML bytes；若偵測到的編碼名稱本身無效或解碼失敗，
    一律 fallback 為 UTF-8 + errors="replace"，確保呼叫端永遠拿得到字串。
    """
    encoding = detect_html_encoding(raw_bytes)
    try:
        return raw_bytes.decode(encoding, errors="replace")
    except (LookupError, ValueError):
        return raw_bytes.decode("utf-8", errors="replace")
