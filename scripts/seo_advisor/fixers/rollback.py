"""從 LocalArchiveConnector.backup() 產生的備份還原檔案。

關鍵安全規則：如果使用者在套用修復之後，又手動編輯過某個檔案，rollback
絕不能用備份覆蓋掉使用者的新改動——那樣會在使用者不知情的情況下丟失他的
工作成果。做法是比對「目前檔案內容的 sha256」與 applied-manifest.json
記錄的「Engineer Mode 寫入完成當下」的 sha256（見 fixers/runner.py 的
`_record_applied_hash`，逐檔案增量寫入，因此即使套用中途失敗，已成功
寫入的檔案仍有記錄可供正確 rollback），只有兩者相符（代表檔案從那之後
沒被動過）才真的還原；不符的話跳過並在 RollbackResult.skipped_paths
裡明確列出，讓使用者自行判斷。

若找不到 applied-manifest.json（例如備份存在但從未真的套用過，或是舊版本
產生的備份），保守地一律跳過所有檔案，不盲目還原。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from seo_advisor.fixers.models import RollbackResult
from seo_advisor.security.safe_archive import resolve_inside_root


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_manifest(backup_path: str) -> dict:
    manifest_path = Path(backup_path) / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"找不到備份 manifest：{manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _load_applied_hashes(backup_path: str) -> dict[str, str] | None:
    applied_path = Path(backup_path) / "applied-manifest.json"
    if not applied_path.exists():
        return None
    return json.loads(applied_path.read_text(encoding="utf-8"))["files"]


def plan_rollback(backup_path: str, *, root: Path) -> tuple[list[str], list[str]]:
    """回傳 (可安全還原的路徑, 需要跳過的路徑)，不實際寫入任何檔案。"""
    manifest = load_manifest(backup_path)
    applied_hashes = _load_applied_hashes(backup_path)
    safe_paths: list[str] = []
    skipped_paths: list[str] = []

    if applied_hashes is None:
        # 沒有 applied-manifest 代表這份備份從未被確認套用過（或是不支援
        # 這個安全機制的舊版備份），無法安全判斷「使用者是否事後改過」，
        # 保守地全部跳過，不猜測。
        return [], list(manifest["files"].keys())

    for rel_path, info in manifest["files"].items():
        current_path = resolve_inside_root(root, rel_path)
        current_exists = current_path.exists()
        expected_hash = applied_hashes.get(rel_path)

        if expected_hash is None:
            skipped_paths.append(rel_path)
            continue

        if not current_exists:
            # 檔案已經不見了（使用者自己刪除，或已被還原過），無需再處理。
            continue

        current_hash = _sha256(current_path.read_bytes())
        if current_hash != expected_hash:
            # 目前內容與「Engineer Mode 寫入完成當下」不一致，代表使用者
            # 之後又動過這個檔案，為避免蓋掉使用者的改動，跳過還原。
            skipped_paths.append(rel_path)
            continue

        safe_paths.append(rel_path)

    return safe_paths, skipped_paths


def rollback(backup_path: str, *, root: Path) -> RollbackResult:
    """實際執行還原。呼叫端必須已驗證過使用者輸入的確認字串。"""
    manifest = load_manifest(backup_path)
    safe_paths, skipped_paths = plan_rollback(backup_path, root=root)

    restored_paths: list[str] = []
    notes: list[str] = []
    for rel_path in safe_paths:
        info = manifest["files"][rel_path]
        target = resolve_inside_root(root, rel_path)
        if info["existed"]:
            backup_file = Path(backup_path) / "files" / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(backup_file.read_bytes())
        else:
            # 備份時檔案不存在，代表這是 Engineer Mode 新建的檔案；
            # 回滾時應該把它刪除，回復到「原本沒有這個檔案」的狀態。
            if target.exists():
                target.unlink()
        restored_paths.append(rel_path)

    if skipped_paths:
        notes.append(
            f"{len(skipped_paths)} 個檔案在套用修復後似乎又被手動修改過（或備份不支援安全回滾判斷），"
            "為避免蓋掉你的改動，已跳過還原這些檔案：" + ", ".join(skipped_paths)
        )

    return RollbackResult(
        backup_id=Path(backup_path).name,
        restored=len(restored_paths) > 0,
        restored_paths=restored_paths,
        skipped_paths=skipped_paths,
        notes=notes,
    )
