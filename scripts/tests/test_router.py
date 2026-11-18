import pytest

from seo_advisor.models import Mode
from seo_advisor.router import UnknownModeError, ensure_implemented, resolve_mode


def test_resolve_mode_handles_aliases():
    assert resolve_mode("consultant") == Mode.CONSULTANT
    assert resolve_mode("audit") == Mode.CONSULTANT
    assert resolve_mode("fix") == Mode.ENGINEER
    assert resolve_mode("security") == Mode.SECURITY
    assert resolve_mode("write") == Mode.CONTENT_WRITER
    assert resolve_mode("plugin") == Mode.PLUGIN_DEV


def test_resolve_mode_unknown_raises():
    with pytest.raises(UnknownModeError):
        resolve_mode("not-a-real-mode")


def test_ensure_implemented_consultant_ok():
    ensure_implemented(Mode.CONSULTANT)  # 不應拋出例外


def test_ensure_implemented_content_writer_ok():
    ensure_implemented(Mode.CONTENT_WRITER)  # 不應拋出例外


def test_ensure_implemented_ecommerce_ok():
    ensure_implemented(Mode.ECOMMERCE)  # 不應拋出例外


def test_resolve_ecommerce_aliases():
    assert resolve_mode("amazon") == Mode.ECOMMERCE
    assert resolve_mode("ecommerce") == Mode.ECOMMERCE


def test_implemented_modes_match_registered_commands():
    from typer.testing import CliRunner
    from seo_advisor.cli import app

    runner = CliRunner()
    for mode in Mode:
        result = runner.invoke(app, ["mode", mode.value])
        assert result.exit_code == 0 and "已實作" in result.output
    assert "WordPress schema-generator" in runner.invoke(app, ["mode", "plugin_dev"]).output
