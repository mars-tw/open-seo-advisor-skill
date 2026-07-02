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

_META_CHARSET_PATTERN = re.compile(rb'<meta[^>]+charset=["\']?([\w-]+)', re.IGNORECASE)

_BOM_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
]


def detect_html_encoding(raw_bytes: bytes) -> str:
    """回傳最可能的編碼名稱（可直接傳給 bytes.decode()）。"""
    for signature, encoding in _BOM_SIGNATURES:
        if raw_bytes.startswith(signature):
            return encoding

    match = _META_CHARSET_PATTERN.search(raw_bytes[:4096])
    if match:
        declared = match.group(1).decode("ascii", errors="ignore").strip().lower()
        if declared:
            return declared

    return "utf-8"


def decode_html_bytes(raw_bytes: bytes) -> str:
    """依偵測到的編碼解碼 HTML bytes；若偵測到的編碼名稱本身無效或解碼失敗，
    一律 fallback 為 UTF-8 + errors="replace"，確保呼叫端永遠拿得到字串。
    """
    encoding = detect_html_encoding(raw_bytes)
    try:
        return raw_bytes.decode(encoding, errors="replace")
    except (LookupError, ValueError):
        return raw_bytes.decode("utf-8", errors="replace")
