import httpx

from seo_advisor.errors import translate_exception
from seo_advisor.url_utils import InvalidUrlError


def test_invalid_url_error_has_actionable_next_steps():
    friendly = translate_exception(InvalidUrlError("網址怪怪的"))
    assert "網址" in friendly.title
    assert len(friendly.next_steps) > 0


def test_connect_timeout_mentions_url():
    friendly = translate_exception(httpx.ConnectTimeout("timeout"), url="https://example.com")
    assert "https://example.com" in friendly.title


def test_connect_error_gives_next_steps():
    friendly = translate_exception(httpx.ConnectError("boom"), url="https://example.com")
    assert len(friendly.next_steps) >= 2


def test_file_not_found_error_translated():
    friendly = translate_exception(FileNotFoundError("no such file"))
    assert "檔案" in friendly.title or "資料夾" in friendly.title


def test_permission_error_translated():
    friendly = translate_exception(PermissionError("denied"))
    assert "權限" in friendly.title


def test_unknown_exception_falls_back_to_generic_message():
    friendly = translate_exception(RuntimeError("something weird"))
    assert "--debug" in " ".join(friendly.next_steps)


def test_render_produces_readable_text():
    friendly = translate_exception(RuntimeError("boom"))
    text = friendly.render()
    assert "[問題]" in text
    assert "建議下一步" in text
