"""LocalArchiveConnector 寫入能力的安全機制測試：capability/dry_run 雙重防護、
atomic write、寫入後 hash 驗證、備份 manifest。"""

from pathlib import Path

import pytest

from seo_advisor.connectors.local_archive import LocalArchiveConnector
from seo_advisor.models import SafetyPolicy


def _write_policy(*, dry_run: bool) -> SafetyPolicy:
    return SafetyPolicy(dry_run=dry_run, allowed_capabilities={"read_urls", "read_files", "write_files"})


def test_capabilities_reflect_policy_write_authorization(tmp_path):
    readonly = LocalArchiveConnector(str(tmp_path))
    assert "write_files" not in readonly.capabilities()

    writable = LocalArchiveConnector(str(tmp_path), policy=_write_policy(dry_run=True))
    assert "write_files" in writable.capabilities()


def test_write_file_without_write_capability_is_rejected(tmp_path):
    connector = LocalArchiveConnector(str(tmp_path))  # 預設 policy 沒有 write_files
    with pytest.raises(PermissionError):
        connector.write_file("robots.txt", b"User-agent: *\n", dry_run=False)


def test_write_file_dry_run_does_not_touch_filesystem(tmp_path):
    connector = LocalArchiveConnector(str(tmp_path), policy=_write_policy(dry_run=True))
    result = connector.write_file("robots.txt", b"User-agent: *\n", dry_run=True)
    assert result.dry_run is True
    assert result.applied is False
    assert not (tmp_path / "robots.txt").exists()


def test_write_file_with_dry_run_policy_rejects_real_write(tmp_path):
    """即使呼叫端傳 dry_run=False，policy.dry_run=True 時仍必須拒絕（雙重防護）。"""
    connector = LocalArchiveConnector(str(tmp_path), policy=_write_policy(dry_run=True))
    with pytest.raises(PermissionError):
        connector.write_file("robots.txt", b"User-agent: *\n", dry_run=False)


def test_write_file_real_write_creates_file_with_exact_content(tmp_path):
    connector = LocalArchiveConnector(str(tmp_path), policy=_write_policy(dry_run=False))
    content = b"User-agent: *\nSitemap: https://example.com/sitemap.xml\n"
    result = connector.write_file("robots.txt", content, dry_run=False)

    assert result.applied is True
    written_path = tmp_path / "robots.txt"
    assert written_path.exists()
    assert written_path.read_bytes() == content


def test_write_file_rejects_path_traversal(tmp_path):
    connector = LocalArchiveConnector(str(tmp_path), policy=_write_policy(dry_run=False))
    with pytest.raises(Exception):
        connector.write_file("../../etc/evil.txt", b"pwned", dry_run=False)


def test_backup_rejects_path_traversal_target(tmp_path):
    """backup() 的 target 路徑也必須被限制在 root 之內，不能透過帶 ../ 的
    target 字串把備份寫到 root 之外（見 fixers 複審發現的問題）。"""
    connector = LocalArchiveConnector(str(tmp_path), policy=_write_policy(dry_run=False))
    with pytest.raises(Exception):
        connector.backup(["../../etc/evil.txt"])


def test_backup_directory_cannot_be_used_as_write_target():
    """.seo-advisor/ 備份目錄本身不該能被當成 Engineer Mode 的修復目標，
    避免誘導寫入/覆蓋備份、破壞 rollback 機制的完整性。"""
    from seo_advisor.fixers.models import UnsafeWriteTargetError, ensure_write_target_allowed

    with pytest.raises(UnsafeWriteTargetError):
        ensure_write_target_allowed(".seo-advisor/backups/x/files/robots.txt")


def test_backup_records_manifest_with_sha256(tmp_path):
    (tmp_path / "robots.txt").write_text("User-agent: *\n", encoding="utf-8")
    connector = LocalArchiveConnector(str(tmp_path), policy=_write_policy(dry_run=False))

    backup_result = connector.backup(["robots.txt"])
    assert backup_result.backup_path is not None

    manifest_path = Path(backup_result.backup_path) / "manifest.json"
    assert manifest_path.exists()

    import json

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["files"]["robots.txt"]["existed"] is True
    assert manifest["files"]["robots.txt"]["sha256"]

    backed_up_file = Path(backup_result.backup_path) / "files" / "robots.txt"
    assert backed_up_file.read_text(encoding="utf-8") == "User-agent: *\n"


def test_backup_records_nonexistent_file_for_new_file_creation(tmp_path):
    connector = LocalArchiveConnector(str(tmp_path), policy=_write_policy(dry_run=False))
    backup_result = connector.backup(["sitemap.xml"])  # 檔案原本不存在

    import json

    manifest = json.loads((Path(backup_result.backup_path) / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"]["sitemap.xml"]["existed"] is False
