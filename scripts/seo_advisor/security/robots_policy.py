"""robots.txt 遵循：判斷指定 URL 是否允許被本工具的 user-agent 爬取。

使用標準庫 `urllib.robotparser`，不引入額外相依套件。任何解析失敗（robots.txt
不存在、格式錯誤、逾時）都視為「允許」，避免因為 robots.txt 本身有問題而讓
整次掃描失敗——這與大多數瀏覽器/爬蟲遇到無法讀取 robots.txt 時的保守做法
一致（fail open，但仍記錄在 coverage notes 供使用者知悉）。
"""

from __future__ import annotations

from urllib.robotparser import RobotFileParser


class RobotsPolicy:
    def __init__(self, robots_txt: str | None, *, user_agent: str) -> None:
        self._user_agent = user_agent
        self._parser: RobotFileParser | None = None

        if robots_txt is None:
            return

        parser = RobotFileParser()
        try:
            parser.parse(robots_txt.splitlines())
            self._parser = parser
        except Exception:
            self._parser = None

    def is_allowed(self, url: str) -> bool:
        if self._parser is None:
            return True
        try:
            return self._parser.can_fetch(self._user_agent, url)
        except Exception:
            return True
