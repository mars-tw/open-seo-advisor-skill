import pytest

from seo_advisor.models import Mode
from seo_advisor.router import ModeNotImplementedError, UnknownModeError, ensure_implemented, resolve_mode


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


def test_ensure_implemented_engineer_raises():
    with pytest.raises(ModeNotImplementedError):
        ensure_implemented(Mode.ENGINEER)
