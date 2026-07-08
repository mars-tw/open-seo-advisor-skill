"""跨平台環境變數設定提示：避免對 Windows 使用者教錯 Bash 語法。

刻意獨立成不依賴任何 provider 的小模組，讓所有 provider（Anthropic/OpenAI/
Meta/...）都能安全 import，不會有循環引用問題。
"""

from __future__ import annotations

import sys


def set_env_var_hint(name: str, placeholder: str = "your-api-key") -> str:
    """給跨平台的『怎麼設定這個環境變數』提示。

    `export FOO=bar` 是 Bash/zsh 語法，在 Windows PowerShell/CMD 完全打不動；
    這裡依 sys.platform 給對應語法。刻意不用 `setx`（會把值持久寫入登錄檔，
    外洩面比僅限當前 session 的 `$env:` 更大），只給當前 session 有效的設定法。
    """
    if sys.platform.startswith("win"):
        return f'請先設定（PowerShell，僅本次視窗有效）：$env:{name}="{placeholder}"'
    return f"請先設定：export {name}={placeholder}"
