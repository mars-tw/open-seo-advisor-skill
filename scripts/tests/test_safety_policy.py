import pytest

from seo_advisor.models import SafetyPolicy


def test_default_policy_only_allows_read_urls():
    policy = SafetyPolicy()
    assert policy.dry_run is True
    assert policy.allowed_capabilities == {"read_urls"}


def test_require_capability_passes_when_allowed():
    policy = SafetyPolicy(allowed_capabilities={"read_urls", "read_files"})
    policy.require_capability("read_files", connector_id="test:example")  # 不應拋出例外


def test_require_capability_raises_when_not_allowed():
    policy = SafetyPolicy(allowed_capabilities={"read_urls"})
    with pytest.raises(PermissionError):
        policy.require_capability("write_files", connector_id="test:example")


def test_require_write_raises_when_dry_run_enabled():
    policy = SafetyPolicy(dry_run=True)
    with pytest.raises(PermissionError):
        policy.require_write(connector_id="test:example")


def test_require_write_passes_when_dry_run_disabled():
    policy = SafetyPolicy(dry_run=False)
    policy.require_write(connector_id="test:example")  # 不應拋出例外
