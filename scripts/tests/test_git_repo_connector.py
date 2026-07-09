"""GitRepoConnector 測試：安全邊界（乾淨 working tree、branch 命名驗證、
branch 已存在拒絕）與 begin/finalize/abort patch session 的核心流程。"""

import subprocess
from pathlib import Path

import pytest

from seo_advisor.connectors.git_repo import (
    BranchAlreadyExistsError,
    DirtyWorkingTreeError,
    GitRepoConnector,
    GitRepoError,
)
from seo_advisor.fixers import runner
from seo_advisor.fixers.models import FixTarget, PatchPlan
from seo_advisor.models import SafetyPolicy


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / "robots.txt").write_text("User-agent: *\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "initial commit")


def _write_policy() -> SafetyPolicy:
    return SafetyPolicy(dry_run=False, allowed_capabilities={"read_urls", "read_files", "write_files"})


def _plan(target_path: str, fixed_content: str) -> PatchPlan:
    return PatchPlan(
        plan_id="fix-SEO-ROBOTS_NO_SITEMAP-001",
        finding_id="SEO-ROBOTS_NO_SITEMAP-001",
        fix_type="robots_txt",
        risk_level="low",
        targets=[
            FixTarget(
                path=target_path,
                original_content="User-agent: *\n",
                fixed_content=fixed_content,
                diff_preview="",
            )
        ],
        summary="test",
    )


def test_rejects_non_git_directory(tmp_path):
    with pytest.raises(GitRepoError):
        GitRepoConnector(str(tmp_path), policy=_write_policy())


def test_begin_session_rejects_dirty_working_tree(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "robots.txt").write_text("dirty change\n", encoding="utf-8")  # 未 commit 的變更

    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())
    plan = _plan("robots.txt", "User-agent: *\nSitemap: https://example.com/sitemap.xml\n")

    with pytest.raises(DirtyWorkingTreeError):
        connector.begin_patch_session(plan)


def test_full_session_creates_branch_and_commit(tmp_path):
    _init_repo(tmp_path)
    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())
    plan = _plan("robots.txt", "User-agent: *\nSitemap: https://example.com/sitemap.xml\n")

    connector.begin_patch_session(plan)
    connector.write_file("robots.txt", plan.targets[0].fixed_content.encode("utf-8"), dry_run=False)
    result = connector.finalize_patch_session(plan)

    assert result.branch.startswith("seo-advisor/fix-")
    assert result.plan_id == plan.plan_id
    assert result.committed_paths == ["robots.txt"]

    # commit 訊息應包含 finding_id 方便追溯
    log = _git(tmp_path, "log", "-1", "--format=%B").stdout
    assert plan.finding_id in log
    assert plan.plan_id in log

    # working tree 現在應該是乾淨的（已經 commit）
    status = _git(tmp_path, "status", "--porcelain").stdout
    assert status.strip() == ""

    # 檔案內容應該反映修復結果
    assert "Sitemap:" in (tmp_path / "robots.txt").read_text(encoding="utf-8")


def test_second_apply_creates_different_branch_since_first_already_committed(tmp_path):
    """跟同名 branch 已存在時拒絕不同：這裡驗證不同的 plan_id 會產生不同的
    branch 名稱，不會互相衝突。"""
    _init_repo(tmp_path)
    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())

    plan1 = _plan("robots.txt", "User-agent: *\nSitemap: https://example.com/sitemap.xml\n")
    connector.begin_patch_session(plan1)
    connector.write_file("robots.txt", plan1.targets[0].fixed_content.encode("utf-8"), dry_run=False)
    result1 = connector.finalize_patch_session(plan1)

    # 切回原本的 branch 並確保乾淨，才能開始第二個 session
    _git(tmp_path, "switch", "main" if _git(tmp_path, "branch", "--list", "main").stdout.strip() else "master")

    plan2 = PatchPlan(
        plan_id="fix-SEO-SITEMAP_MISSING-002",
        finding_id="SEO-SITEMAP_MISSING-002",
        fix_type="sitemap",
        risk_level="low",
        targets=[FixTarget(path="sitemap.xml", original_content="", fixed_content="<urlset/>", diff_preview="")],
        summary="test2",
    )
    connector2 = GitRepoConnector(str(tmp_path), policy=_write_policy())
    connector2.begin_patch_session(plan2)
    connector2.write_file("sitemap.xml", plan2.targets[0].fixed_content.encode("utf-8"), dry_run=False)
    result2 = connector2.finalize_patch_session(plan2)

    assert result1.branch != result2.branch


def test_begin_session_rejects_existing_branch_name(tmp_path):
    _init_repo(tmp_path)
    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())
    plan = _plan("robots.txt", "User-agent: *\nSitemap: https://example.com/sitemap.xml\n")

    connector.begin_patch_session(plan)
    connector.write_file("robots.txt", plan.targets[0].fixed_content.encode("utf-8"), dry_run=False)
    connector.finalize_patch_session(plan)

    # 切回原本 branch，再次用同一個 plan 嘗試建立同名 branch，應該被拒絕
    default_branch = _git(tmp_path, "branch", "--list", "main").stdout.strip() or "master"
    _git(tmp_path, "switch", default_branch.lstrip("* "))

    connector2 = GitRepoConnector(str(tmp_path), policy=_write_policy())
    with pytest.raises(BranchAlreadyExistsError):
        connector2.begin_patch_session(plan)


def test_finalize_without_begin_session_raises(tmp_path):
    _init_repo(tmp_path)
    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())
    plan = _plan("robots.txt", "content")

    with pytest.raises(GitRepoError):
        connector.finalize_patch_session(plan)


def test_double_begin_session_raises(tmp_path):
    _init_repo(tmp_path)
    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())
    plan = _plan("robots.txt", "content")

    connector.begin_patch_session(plan)
    with pytest.raises(GitRepoError):
        connector.begin_patch_session(plan)


def test_abort_session_restores_original_branch_and_deletes_new_branch(tmp_path):
    _init_repo(tmp_path)
    original_branch = _git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())
    plan = _plan("robots.txt", "User-agent: *\nSitemap: https://example.com/sitemap.xml\n")

    connector.begin_patch_session(plan)
    new_branch = connector._session_branch
    connector.write_file("robots.txt", plan.targets[0].fixed_content.encode("utf-8"), dry_run=False)
    connector.abort_patch_session(plan)

    assert _git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == original_branch
    branch_list = _git(tmp_path, "branch", "--list", new_branch).stdout
    assert branch_list.strip() == ""  # 新 branch 已被刪除

    # 原本的檔案內容應該完全沒有被異動
    assert (tmp_path / "robots.txt").read_text(encoding="utf-8") == "User-agent: *\n"


def test_finalize_without_actual_write_aborts_and_raises(tmp_path):
    """若呼叫端忘記在 begin/finalize 之間呼叫 write_file()（檔案內容完全
    沒有變動），暫存區驗證應該偵測到「預期有變更但實際沒有」而拒絕 commit，
    而不是靜默 commit 一個空的變更。"""
    _init_repo(tmp_path)
    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())
    plan = _plan("robots.txt", "User-agent: *\nSitemap: https://example.com/sitemap.xml\n")

    connector.begin_patch_session(plan)
    # 故意不呼叫 write_file()，直接 finalize
    with pytest.raises(GitRepoError):
        connector.finalize_patch_session(plan)

    # session 應該已經被安全中止，repo 回到原本的 branch 且乾淨
    original_branch = "main" if _git(tmp_path, "branch", "--list", "main").stdout.strip() else "master"
    assert _git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == original_branch
    assert _git(tmp_path, "status", "--porcelain").stdout.strip() == ""


def test_finalize_rejects_unexpected_extra_staged_file(tmp_path):
    """若 working tree 中意外多了一個不在 plan targets 裡的變更被 staged，
    finalize 必須拒絕 commit，避免把非預期的檔案一併提交進 PR。"""
    _init_repo(tmp_path)
    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())
    plan = _plan("robots.txt", "User-agent: *\nSitemap: https://example.com/sitemap.xml\n")

    connector.begin_patch_session(plan)
    connector.write_file("robots.txt", plan.targets[0].fixed_content.encode("utf-8"), dry_run=False)

    # 模擬「意外」在同一個 branch 上多了一個未預期的檔案
    (tmp_path / "sitemap.xml").write_text("<urlset/>", encoding="utf-8")
    _git(tmp_path, "add", "sitemap.xml")

    with pytest.raises(GitRepoError):
        connector.finalize_patch_session(plan)


# --- runner.apply_plan() 與 GitRepoConnector 的整合 ---


def test_apply_plan_with_git_connector_creates_branch_and_commit(tmp_path):
    """apply_plan() 偵測到 connector 支援 begin_patch_session 時，應該自動
    走 git branch+commit 流程，呼叫端不需要手動呼叫 begin/finalize。"""
    _init_repo(tmp_path)
    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())
    plan = _plan("robots.txt", "User-agent: *\nSitemap: https://example.com/sitemap.xml\n")

    result = runner.apply_plan(plan, connector=connector)

    assert result.applied is True
    assert any("分支" in note for note in result.validation_notes)
    # working tree 現在應該乾淨（已經 commit），且回到新 branch 上
    assert _git(tmp_path, "status", "--porcelain").stdout.strip() == ""
    current_branch = _git(tmp_path, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    assert current_branch.startswith("seo-advisor/fix-")


def test_apply_plan_with_git_connector_on_dirty_tree_fails_before_writing(tmp_path):
    """apply_plan() 透過 begin_patch_session 檢查乾淨度，dirty tree 時應在
    寫入任何檔案之前就失敗，不會有部分寫入的中間狀態。"""
    _init_repo(tmp_path)
    (tmp_path / "robots.txt").write_text("dirty\n", encoding="utf-8")

    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())
    plan = _plan("robots.txt", "User-agent: *\nSitemap: https://example.com/sitemap.xml\n")

    with pytest.raises(DirtyWorkingTreeError):
        runner.apply_plan(plan, connector=connector)

    # 檔案內容應該還是使用者自己弄髒的那個版本，不受影響
    assert (tmp_path / "robots.txt").read_text(encoding="utf-8") == "dirty\n"


def test_backup_lives_inside_git_directory_not_working_tree(tmp_path):
    """備份必須放在 .git/ 內部而非 working tree 之內，否則會讓
    `git status` 出現未追蹤的 .seo-advisor/ 目錄，違背「乾淨 working tree」
    這個核心承諾。"""
    _init_repo(tmp_path)
    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())
    plan = _plan("robots.txt", "User-agent: *\nSitemap: https://example.com/sitemap.xml\n")

    runner.apply_plan(plan, connector=connector)

    assert not (tmp_path / ".seo-advisor").exists()
    assert (tmp_path / ".git" / "seo-advisor-backups-root" / ".seo-advisor" / "backups").exists()
    assert _git(tmp_path, "status", "--porcelain").stdout.strip() == ""


def test_begin_session_rejects_detached_head(tmp_path):
    """detached HEAD 狀態下沒有具名分支可以「切回」，begin_patch_session
    必須拒絕，而不是把字面字串 "HEAD" 當成原本的分支名稱。"""
    _init_repo(tmp_path)
    head_sha = _git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    _git(tmp_path, "checkout", "-q", head_sha)

    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())
    plan = _plan("robots.txt", "User-agent: *\nSitemap: https://example.com/sitemap.xml\n")

    with pytest.raises(GitRepoError, match="detached HEAD"):
        connector.begin_patch_session(plan)


def test_begin_session_rejects_gitignored_target(tmp_path):
    """若 target 檔案被 .gitignore 忽略（且從未被 git 追蹤——.gitignore
    對已追蹤的檔案不生效，這是真實情境的關鍵前提），begin_patch_session
    必須在寫入任何內容之前就拒絕。因為寫入後即使 abort，git reset --hard
    也無法恢復被 ignore 的檔案原本的內容（沒有版本歷史可還原），會造成
    無法挽回的資料遺失。這裡驗證的是「使用者原本手動放的、被 ignore 的
    sitemap.xml 內容在整個流程後完全不變」。
    """
    repo = tmp_path
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    (repo / ".gitignore").write_text("sitemap.xml\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-q", "-m", "initial commit with gitignore")
    # sitemap.xml 從未被 git add，只是使用者手動放在檔案系統裡、被 .gitignore 蓋住。
    (repo / "sitemap.xml").write_text("<urlset><!-- 使用者手動維護的內容 --></urlset>", encoding="utf-8")

    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())
    plan = _plan("sitemap.xml", "<urlset/>")

    with pytest.raises(GitRepoError, match="gitignore"):
        connector.begin_patch_session(plan)

    # 核心斷言：使用者原本手動維護的 sitemap.xml 內容完全沒有被動過。
    assert (tmp_path / "sitemap.xml").read_text(encoding="utf-8") == (
        "<urlset><!-- 使用者手動維護的內容 --></urlset>"
    )


def test_stale_session_marker_blocks_further_operations(tmp_path):
    """模擬程序在 begin_patch_session 成功之後、finalize/abort 之前被強制
    中斷（例如 Ctrl+C）：下一次建立新的 GitRepoConnector 實例時，必須偵測
    到殘留的 session marker 並拒絕繼續，而不是誤判 working tree 乾淨就
    繼續操作、蓋掉上次未完成 session 的狀態。"""
    _init_repo(tmp_path)
    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())
    plan = _plan("robots.txt", "User-agent: *\nSitemap: https://example.com/sitemap.xml\n")

    connector.begin_patch_session(plan)
    # 模擬「中斷」：不呼叫 finalize 或 abort，程序假裝在這裡結束。
    # session marker 檔案應該還留在 .git 內。

    with pytest.raises(GitRepoError, match="上一次的修復 session"):
        GitRepoConnector(str(tmp_path), policy=_write_policy())


def test_begin_session_rejects_submodule_target(tmp_path):
    """target 落在 submodule 內（git ls-files --stage 顯示 mode 160000
    的 gitlink）時，git add/commit 語義是記錄子 repo 的 commit SHA 而非
    實際檔案內容，我們的邏輯完全沒有處理這種情況，必須拒絕。"""
    sub_repo = tmp_path.parent / f"{tmp_path.name}_sub"
    sub_repo.mkdir()
    _git(sub_repo, "init", "-q")
    _git(sub_repo, "config", "user.email", "test@example.com")
    _git(sub_repo, "config", "user.name", "Test User")
    (sub_repo / "robots.txt").write_text("User-agent: *\n", encoding="utf-8")
    _git(sub_repo, "add", "-A")
    _git(sub_repo, "commit", "-q", "-m", "sub init")

    tmp_path.mkdir(parents=True, exist_ok=True)
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test User")
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "parent init")
    subprocess.run(
        ["git", "-c", "protocol.file.allow=always", "-C", str(tmp_path),
         "submodule", "add", str(sub_repo), "subrepo"],
        capture_output=True, text=True, check=True,
    )
    _git(tmp_path, "commit", "-q", "-m", "add submodule")

    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())
    plan = _plan("subrepo/robots.txt", "User-agent: *\nSitemap: https://example.com/sitemap.xml\n")

    with pytest.raises(GitRepoError, match="submodule"):
        connector.begin_patch_session(plan)


def test_concurrent_session_marker_creation_is_atomic(tmp_path):
    """模擬兩個程序幾乎同時通過 stale-session 檢查、都嘗試建立 session
    marker 的競爭情境：第二個呼叫必須因為檔案已存在而失敗，不能讓兩個
    session 都「成功」建立並各自建立分支、互相踩到對方的狀態。"""
    _init_repo(tmp_path)
    connector = GitRepoConnector(str(tmp_path), policy=_write_policy())
    plan = _plan("robots.txt", "User-agent: *\nSitemap: https://example.com/sitemap.xml\n")

    # 手動模擬「已經有一個 session marker 存在」（略過完整 begin_patch_session
    # 讓 marker 提早就位，代表另一個程序已經搶先建立了自己的 session）。
    connector._session_marker_path.parent.mkdir(parents=True, exist_ok=True)
    connector._session_marker_path.write_text('{"plan_id": "other"}', encoding="utf-8")

    with pytest.raises(GitRepoError, match="另一個 GitRepoConnector session"):
        connector._write_session_marker(plan)
