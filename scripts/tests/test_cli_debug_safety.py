"""鎖住 --debug 模式的安全設定，防止未來升級 typer 或改動預設值時，
無聲引入「traceback 印出每層 stack frame 區域變數（可能含 API 金鑰）」的風險。

背景：--debug 模式會直接 raise 原始例外讓 Rich 印出完整 traceback，這對
除錯是必要的；但 Rich/typer 的 pretty traceback 若開啟 show_locals，會連同
每個 stack frame 裡的區域變數一起印出（例如 provider 建構子裡讀出的
api_key 變數），即使該例外訊息本身沒有洩漏敏感資訊，也可能被 traceback
的區域變數面板意外洩漏。
"""

from seo_advisor.cli import app


def test_pretty_exceptions_show_locals_is_disabled():
    assert app.pretty_exceptions_show_locals is False
