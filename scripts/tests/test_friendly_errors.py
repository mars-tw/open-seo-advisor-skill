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


# --- 敏感資訊遮蔽（避免錯誤訊息洩漏 token/帳密/本機路徑）---

def test_redact_url_userinfo():
    from seo_advisor.errors import redact_secrets

    out = redact_secrets("connect failed https://admin:s3cret@internal.host/x")
    assert "s3cret" not in out
    assert "admin" not in out


def test_redact_token_assignment():
    from seo_advisor.errors import redact_secrets

    assert "sk-abc123" not in redact_secrets("error api_key=sk-abc123def")
    assert "xyz789" not in redact_secrets("Authorization: xyz789")


def test_redact_home_path():
    from seo_advisor.errors import redact_secrets

    assert "digimkt" not in redact_secrets(r"open C:\Users\digimkt\file.txt")
    assert "alice" not in redact_secrets("open /home/alice/file.txt")


def test_friendly_error_render_redacts():
    from seo_advisor.errors import FriendlyError

    fe = FriendlyError(
        title="failed for https://u:p@h/x",
        reasons=["token=deadbeef leaked"],
        next_steps=["retry"],
    )
    rendered = fe.render()
    assert "deadbeef" not in rendered
    assert "u:p@h" not in rendered
