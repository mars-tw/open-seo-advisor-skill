"""強制 stdout/stderr 使用 UTF-8 輸出。

Windows 上的 Python 預設會用系統的舊版編碼（如 cp950/Big5）輸出到終端機，
導致中文訊息在原生 PowerShell/CMD 中顯示成亂碼，即使終端機本身已經支援
UTF-8（例如執行過 `chcp 65001`）。這個模組必須在任何會印出中文訊息的模組
（尤其是 rich.Console）被匯入之前執行，因此在 seo_advisor/__init__.py 的
最開頭呼叫。
"""

from __future__ import annotations

import sys


def ensure_utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except ValueError:
                pass
