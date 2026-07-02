"""強制 stdin/stdout/stderr 使用 UTF-8。

Windows 上的 Python 預設會用系統的舊版編碼（如 cp950/Big5）讀寫終端機：
- 輸出：中文訊息在原生 PowerShell/CMD 顯示成亂碼（即使已 chcp 65001）。
- 輸入：透過 pipe 或互動精靈輸入中文時，可能讀成 surrogate 而在後續寫檔爆掉。

這個模組必須在任何會讀寫中文的模組（尤其 rich.Console 與互動 Prompt）被
匯入之前執行，因此在 seo_advisor/__init__.py 的最開頭呼叫。
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
    # stdin 用 errors="replace"：即使收到不合法位元組也不讓整個程式崩潰，
    # 而是以替代字元讀入，維持互動精靈對新手的穩定性。
    if hasattr(sys.stdin, "reconfigure"):
        try:
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        except ValueError:
            pass
