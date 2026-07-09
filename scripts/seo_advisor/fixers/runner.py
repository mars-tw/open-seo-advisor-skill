"""Engineer Mode 的執行入口：Finding → PatchPlan → （確認後）套用 → FixResult。

安全流程（呼叫端 CLI 必須照這個順序走，不可跳過任何一步）：
1. build_plan()：只讀取，永遠安全，產出 PatchPlan（dry-run 預覽）。
2. 呼叫端把 PatchPlan 完整呈現給使用者（含 diff、風險等級、警告）。
3. 使用者輸入 fixers.safety.build_apply_confirmation(plan.plan_id) 對應的
   確認字串，呼叫端驗證通過後才呼叫 apply_plan()。
4. apply_plan() 內部：若 connector 支援 begin_patch_session（目前只有
   GitRepoConnector）就先呼叫它建立新 branch → backup() → 逐一
   write_file(dry_run=False)，每寫入一個檔案就立刻把該檔案的 hash 增量
   寫進 applied-manifest.json → 若支援則呼叫 finalize_patch_session()
   commit 變更 → 回傳 FixResult。任何一步失敗就停止：LocalArchiveConnector
   模式下已成功寫入的部分因為 applied-manifest 已經即時記錄，rollback
   仍能正確識別並還原；GitRepoConnector 模式下則呼叫 abort_patch_session()
   把整個 session 復原（reset 到套用前的 commit、切回原 branch、刪除新
   branch），因為半途而廢的 commit 沒有意義——PR 應該是一個完整的修復，
   不是「寫了一半的檔案」。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from seo_advisor.connectors.base import WebsiteConnector
from seo_advisor.crawler import CrawlResult
from seo_advisor.fixers import canonical, robots, sitemap
from seo_advisor.fixers.models import FixResult, NotFixableError, PatchPlan
from seo_advisor.models import Finding

_FIXERS = (robots, sitemap, canonical)


def find_fixer(finding: Finding):
    for module in _FIXERS:
        if module.can_fix(finding):
            return module
    return None


def list_fixable_findings(findings: list[Finding]) -> list[Finding]:
    """回傳這批 findings 裡，目前有對應自動修復邏輯的項目。"""
    return [f for f in findings if find_fixer(f) is not None]


def build_plan(
    finding: Finding,
    *,
    connector: WebsiteConnector,
    crawl_result: CrawlResult,
    seed_url: str,
) -> PatchPlan:
    """為單一 Finding 產出修復計畫。只讀取，不寫入任何檔案。"""
    module = find_fixer(finding)
    if module is None:
        raise NotFixableError(f"{finding.id} 目前沒有對應的自動修復邏輯。")

    if module is robots:
        current = None
        try:
            current = connector.read_file("robots.txt").decode("utf-8", errors="replace")
        except FileNotFoundError:
            current = None
        return robots.plan_fix(finding, current_content=current, seed_url=seed_url)

    if module is sitemap:
        site_origin = seed_url if seed_url.startswith(("http://", "https://")) else None
        indexable_urls = []
        for url, snapshot in crawl_result.pages.items():
            if snapshot.status_code != 200:
                continue
            if "noindex" in snapshot.headers.get("x-robots-tag", "").lower():
                continue
            resolved = snapshot.final_url or url
            if site_origin and not resolved.startswith(("http://", "https://")):
                resolved = site_origin.rstrip("/") + "/" + resolved.lstrip("/")
            indexable_urls.append(resolved)
        return sitemap.plan_fix(finding, indexable_urls=indexable_urls)

    if module is canonical:
        pages = {
            url: snapshot.html
            for url, snapshot in crawl_result.pages.items()
            if snapshot.status_code == 200 and snapshot.html
        }
        return canonical.plan_fix(finding, pages=pages)

    raise NotFixableError(f"{finding.id} 的 fixer 尚未串接執行邏輯。")  # pragma: no cover


def apply_plan(plan: PatchPlan, *, connector: WebsiteConnector) -> FixResult:
    """套用一份已經過使用者確認的 PatchPlan。

    呼叫端必須在呼叫這個函式之前，已經驗證過使用者輸入的確認字串與
    plan.plan_id 相符（見 fixers/safety.py），這裡不重複驗證確認字串本身，
    只負責安全地執行寫入。
    """
    supports_git_session = hasattr(connector, "begin_patch_session")
    if supports_git_session:
        connector.begin_patch_session(plan)

    backup_result = connector.backup([target.path for target in plan.targets])

    written_paths: list[str] = []
    validation_notes: list[str] = []
    try:
        for target in plan.targets:
            patch_result = connector.write_file(
                target.path, target.fixed_content.encode("utf-8"), dry_run=False
            )
            if not patch_result.applied:
                raise OSError(f"{target.path} 寫入未成功套用，已停止後續檔案的寫入。")
            written_paths.append(target.path)
            # 每寫入一個檔案就立刻記錄它的 applied hash，即使後面的檔案
            # 失敗，這個檔案仍然可以被正確 rollback（見模組 docstring）。
            if backup_result.backup_path:
                _record_applied_hash(backup_result.backup_path, plan.plan_id, target)

        git_result = None
        if supports_git_session:
            # git 模式下，半途而廢的 commit 沒有意義，finalize 失敗（例如
            # 暫存區內容與預期不符）一律視為整個 apply 失敗並復原。
            git_result = connector.finalize_patch_session(plan)
    except Exception as exc:
        if supports_git_session:
            connector.abort_patch_session(plan)
            validation_notes.append(
                f"套用中斷：{exc}。GitRepoConnector 已自動復原（reset 新 branch、"
                "切回原本的 branch 並刪除新 branch），working tree 沒有任何殘留變更。"
            )
        else:
            validation_notes.append(
                f"套用中斷：{exc}。已寫入 {len(written_paths)}/{len(plan.targets)} 個檔案，"
                f"其餘檔案未變動。已寫入的部分可用 backup_id={backup_result.backup_path} 回滾。"
            )
        return FixResult(
            plan_id=plan.plan_id,
            applied=False,
            backup_id=backup_result.backup_path,
            written_paths=written_paths,
            validation_passed=False,
            validation_notes=validation_notes,
        )

    if git_result is not None:
        validation_notes.append(
            f"已建立分支 {git_result.branch} 並 commit（{git_result.commit_sha[:8]}），"
            f"包含 {len(git_result.committed_paths)} 個檔案。"
            f"請自行 review 後執行：git push -u origin {git_result.branch}"
        )
    else:
        validation_notes.append(f"已寫入 {len(written_paths)} 個檔案：{', '.join(written_paths)}")

    return FixResult(
        plan_id=plan.plan_id,
        applied=True,
        backup_id=backup_result.backup_path,
        written_paths=written_paths,
        validation_passed=True,
        validation_notes=validation_notes,
    )


def _record_applied_hash(backup_path: str, plan_id: str, target) -> None:
    """把單一檔案「Engineer Mode 寫入完成當下」的 sha256 增量寫進
    applied-manifest.json，供 rollback 判斷使用者是否在套用之後又手動
    修改過該檔案（見 fixers/rollback.py）。用讀取-合併-寫回而非整批覆寫，
    確保先前已記錄的檔案不會因為後續檔案的記錄動作而遺失。
    """
    manifest_path = Path(backup_path, "applied-manifest.json")
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        data = {"plan_id": plan_id, "files": {}}

    data["files"][target.path] = hashlib.sha256(target.fixed_content.encode("utf-8")).hexdigest()
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
