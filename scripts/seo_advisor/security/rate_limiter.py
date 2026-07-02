"""簡單的固定速率限制器，讓 HTTPConnector 不會對目標主機發送過於密集的請求。"""

from __future__ import annotations

import time


class RateLimiter:
    """每次呼叫 wait() 會確保與上一次呼叫至少間隔 `1 / requests_per_second` 秒。"""

    def __init__(self, requests_per_second: float) -> None:
        self._min_interval = 1.0 / requests_per_second if requests_per_second > 0 else 0.0
        self._last_call: float | None = None

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        now = time.monotonic()
        if self._last_call is not None:
            elapsed = now - self._last_call
            remaining = self._min_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_call = time.monotonic()
