"""跨平台環境變數設定提示：Windows 不該被教 Bash 的 export 語法。"""

from unittest.mock import patch

from seo_advisor.env_hints import set_env_var_hint


def test_windows_uses_powershell_syntax():
    with patch("seo_advisor.env_hints.sys") as mock_sys:
        mock_sys.platform = "win32"
        hint = set_env_var_hint("ANTHROPIC_API_KEY")
    assert "$env:" in hint
    assert "export" not in hint
    assert "setx" not in hint  # 不用 setx：避免把金鑰持久寫入登錄檔


def test_unix_uses_export_syntax():
    with patch("seo_advisor.env_hints.sys") as mock_sys:
        mock_sys.platform = "linux"
        hint = set_env_var_hint("ANTHROPIC_API_KEY")
    assert "export ANTHROPIC_API_KEY=" in hint


def test_macos_uses_export_syntax():
    with patch("seo_advisor.env_hints.sys") as mock_sys:
        mock_sys.platform = "darwin"
        hint = set_env_var_hint("OPENAI_API_KEY")
    assert "export OPENAI_API_KEY=" in hint


def test_custom_placeholder_is_used():
    with patch("seo_advisor.env_hints.sys") as mock_sys:
        mock_sys.platform = "linux"
        hint = set_env_var_hint("META_ACCESS_TOKEN", "your-access-token")
    assert "your-access-token" in hint
