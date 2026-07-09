"""GitRepoConnector：操作本機已存在的 git repo，讓 Engineer Mode 的修復結果
產出一個可以直接 `git push` 開 PR 的 branch + commit，而不是直接覆蓋使用者
目前 working tree 的內容。

這不是一種新的「網站接入方式」（不像 SSHConnector/WordPressAPIConnector
需要連到使用者的遠端伺服器/帳號）——純粹操作本機檔案系統上已存在的 .git
repo，不涉及任何遠端連線、不需要 SSH key 或 HTTPS 認證、不會自動 push。

安全設計（務必先讀）：
- 只在完全乾淨的 working tree 上運作（`git status --porcelain` 必須空）。
  不接受 staged/unstaged/untracked 變更，避免把使用者尚未提交的檔案意外
  混進 commit，也避免失敗時的自動還原邏輯誤傷使用者的既有工作。
- 新 branch 的名稱必須通過 `git check-ref-format --branch` 驗證；若使用者
  指定的 branch 已存在，直接拒絕，絕不覆蓋或切換過去重用。
- 所有 git 操作透過 subprocess 的 list-args 形式呼叫（不經過 shell），
  且路徑一律加 `--` pathspec 分隔符，避免任何形式的引數/pathspec 注入。
- 寫入內容仍必須先通過 fixers/models.py 的 ensure_write_target_allowed()
  與 connectors/base.py 的 resolve_inside_root()（本模組直接複用
  LocalArchiveConnector 的 write_file 實作邏輯，不重新發明一套）。
- commit 前會驗證 staged 內容精確等於這次 patch session 的 target 清單，
  避免任何非預期的檔案被一併提交。
- 任何步驟失敗，一律嘗試把 repo 恢復到套用前的狀態（reset 到 base commit、
  切回原 branch、刪除剛建立的新 branch），且只在「這個新 branch 是這次
  session 剛建立、開始時 repo 確實乾淨」的前提下才執行這個自動復原。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from seo_advisor.connectors.local_archive import LocalArchiveConnector
from seo_advisor.models import GitPatchResult, SafetyPolicy

_BRANCH_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._/-]+$")


class GitRepoError(RuntimeError):
    """git 操作失敗，或 repo 狀態不符合 GitRepoConnector 要求時拋出。"""


class DirtyWorkingTreeError(GitRepoError):
    """working tree 不乾淨（有 staged/unstaged/untracked 變更）時拋出。"""


class BranchAlreadyExistsError(GitRepoError):
    """要建立的 branch 名稱已經存在時拋出。"""


def _run_git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    """在指定 repo 執行 git 指令，list-args 形式（不經過 shell），
    任何呼叫端傳入的路徑參數都必須由呼叫者自行加上 "--" pathspec 分隔符。
    """
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )


def _validate_branch_name(repo_root: Path, branch: str) -> None:
    if not _BRANCH_NAME_PATTERN.match(branch):
        raise GitRepoError(
            f"分支名稱 {branch!r} 含有不允許的字元，只能使用英數字、"
            "'.'、'_'、'/'、'-'。"
        )
    result = _run_git(repo_root, "check-ref-format", "--branch", branch)
    if result.returncode != 0:
        raise GitRepoError(f"分支名稱 {branch!r} 不是合法的 git ref 名稱：{result.stderr.strip()}")


class GitRepoConnector(LocalArchiveConnector):
    """在 LocalArchiveConnector 的檔案讀寫邏輯之上，加上 git branch/commit
    的 patch session 管理。write_file()/backup()/read_file() 等皆直接繼承
    LocalArchiveConnector 的實作（同一套白名單、atomic write、備份機制），
    這裡只新增 begin/finalize/abort 三個 session 方法。
    """

    def __init__(self, repo_path: str, *, policy: SafetyPolicy | None = None) -> None:
        super().__init__(repo_path, policy=policy)
        if not (self.root / ".git").exists():
            raise GitRepoError(f"{repo_path} 不是一個 git repo（找不到 .git 目錄）。")

        # 用 `git rev-parse --git-dir` 取得實際的 git 目錄，而不是硬假設
        # "<root>/.git" 是一個目錄——在 worktree/submodule 情境下 .git 可能
        # 是一個指向別處的檔案（gitfile），直接用 self.root / ".git" 拼路徑
        # 會指向錯誤或不存在的位置。
        git_dir_result = _run_git(self.root, "rev-parse", "--git-dir")
        if git_dir_result.returncode != 0:
            raise GitRepoError(f"無法取得 git 目錄：{git_dir_result.stderr.strip()}")
        git_dir = (self.root / git_dir_result.stdout.strip()).resolve()

        # 備份與 session marker 都放在 .git 目錄內部（而非 repo working tree
        # 之內），因為 .git 內容本身永遠不會出現在 `git status` 的追蹤範圍
        # ——這樣「乾淨的 working tree」這個核心承諾才是名副其實。
        self._backup_root = git_dir / "seo-advisor-backups-root"
        self._session_marker_path = git_dir / "seo-advisor-session.json"

        self._session_branch: str | None = None
        self._session_base_commit: str | None = None
        self._session_original_branch: str | None = None
        self._session_targets: list[str] = []

        self._reject_stale_session()

    def id(self) -> str:
        return f"git_repo:{self.root}"

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return _run_git(self.root, *args)

    def _current_branch(self) -> str:
        """回傳目前所在的 branch 名稱；若處於 detached HEAD 狀態則拋出例外
        （而不是回傳字面字串 "HEAD"，那不是合法的 branch 名稱，若被誤用於
        後續 abort_patch_session 的 `git switch <branch>` 會執行失敗或
        產生非預期行為）。"""
        result = self._git("symbolic-ref", "--quiet", "--short", "HEAD")
        if result.returncode != 0:
            raise GitRepoError(
                "目前處於 detached HEAD 狀態（沒有 checkout 到任何具名分支），"
                "GitRepoConnector 無法安全地知道套用失敗時該切回哪個分支，"
                "請先 `git switch` 到一個具名分支再重試。"
            )
        return result.stdout.strip()

    def _is_working_tree_clean(self) -> bool:
        """檢查 working tree 是否乾淨。備份放在 `.git/` 內部（見 __init__
        對 _backup_root 的覆寫），.git/ 本身永遠不會出現在 git status 的
        追蹤範圍內，因此這裡不需要額外排除任何路徑。
        """
        result = self._git("status", "--porcelain")
        return result.returncode == 0 and result.stdout.strip() == ""

    def _reject_stale_session(self) -> None:
        """建構子呼叫：若偵測到上一次的 patch session 沒有正常結束（例如
        程序在 begin_patch_session 之後、finalize/abort 之前被強制中斷，
        像是 Ctrl+C 或系統崩潰），拒絕繼續操作，並提示使用者手動確認狀態。

        這是必要的機制：若沒有這個檢查，使用者可能停在一個
        `seo-advisor/fix-*` 分支上，working tree 剛好是乾淨的（例如中斷點
        剛好卡在 write_file 之前），下一次執行會誤判「乾淨可以繼續」，
        卻沒發現自己其實還站在上次未完成的分支、base commit 記錄也對不上
        這一次的操作。
        """
        if not self._session_marker_path.exists():
            return
        try:
            marker = json.loads(self._session_marker_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            marker = {}
        raise GitRepoError(
            "偵測到上一次的修復 session 沒有正常結束（可能是中途被中斷），"
            f"殘留分支：{marker.get('branch', '未知')}，"
            f"原本分支：{marker.get('original_branch', '未知')}。"
            "為避免在不確定的狀態上繼續操作，已拒絕執行。請手動確認 repo 狀態"
            "（`git branch` 查看是否停在該分支、`git log` 確認有無非預期 commit），"
            f"確認安全後刪除 {self._session_marker_path} 再重試。"
        )

    def _write_session_marker(self, plan) -> None:
        """原子地建立 session marker 檔案，同時作為簡易的 repo-level lock：
        用 O_CREAT | O_EXCL 開啟，若檔案已存在（代表有另一個程序在
        `_reject_stale_session()` 檢查之後、這裡寫入之前搶先建立了自己的
        session），open() 會拋出 FileExistsError，避免兩個程序的 patch
        session 在極短的時間窗內同時通過檢查、互相踩到對方的 branch/commit
        狀態。
        """
        self._session_marker_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "plan_id": plan.plan_id,
                "finding_id": plan.finding_id,
                "branch": self._session_branch,
                "original_branch": self._session_original_branch,
                "base_commit": self._session_base_commit,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        try:
            fd = os.open(str(self._session_marker_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise GitRepoError(
                "另一個 GitRepoConnector session 剛好同時搶先建立了 session marker，"
                "為避免兩個修復流程互相干擾，已拒絕這次操作，請稍後重試。"
            ) from exc
        with os.fdopen(fd, "wb") as f:
            f.write(payload)

    def _clear_session_marker(self) -> None:
        self._session_marker_path.unlink(missing_ok=True)

    def _list_submodule_paths(self) -> list[str]:
        """回傳這個 repo 已知的 submodule 路徑清單（相對於 repo root）。
        submodule 內部的個別檔案不會出現在 `git ls-files --stage` 裡（parent
        repo 只記錄一個指向子 repo commit 的 gitlink），必須另外用
        `git config --file .gitmodules` 或 `submodule status` 取得路徑
        清單，再用路徑前綴比對 target 是否落在裡面。
        """
        result = self._git("config", "--file", ".gitmodules", "--get-regexp", r"\.path$")
        if result.returncode != 0:
            return []
        paths = []
        for line in result.stdout.splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                paths.append(parts[1].strip())
        return paths

    def _reject_unsafe_targets(self, plan) -> None:
        """在建立新 branch 之前，逐一檢查 plan.targets 是否落在不安全的
        情境：被 .gitignore 忽略、或落在 submodule 內。任何一項不符就拒絕
        整個 session，不寫入任何檔案。
        """
        submodule_paths = self._list_submodule_paths()

        for target in plan.targets:
            # 被 .gitignore 忽略：`git status --porcelain` 不會顯示被 ignore
            # 的檔案，所以「working tree 乾淨」的檢查偵測不到這種情況；但
            # write_file() 仍會覆寫它的內容，而 abort_patch_session() 的
            # `git reset --hard` 完全不會恢復被 ignore 的檔案（git 從未
            # 追蹤它、沒有版本歷史可以恢復）——這是真實驗證過的資料遺失
            # 風險，不是理論上的邊界案例。
            ignore_result = self._git("check-ignore", "--quiet", "--", target.path)
            if ignore_result.returncode == 0:
                raise GitRepoError(
                    f"{target.path!r} 被 .gitignore 規則忽略。git-branch 模式下若寫入這個檔案，"
                    "之後即使 abort 也無法用 git 復原它原本的內容（因為 git 從未追蹤這個檔案），"
                    "為避免造成無法挽回的資料遺失，已拒絕整個 session。"
                    "請先調整 .gitignore 或改用 --write-mode direct。"
                )

            # 落在 submodule 內：parent repo 對 submodule 路徑的 add/commit
            # 語義是記錄一個 gitlink（指向子 repo 的 commit SHA），submodule
            # 內部的個別檔案完全不在 parent repo 的追蹤範圍內，我們的
            # write_file()/staged-path 驗證邏輯完全沒有考慮這種情況，貿然
            # 處理可能寫壞子 repo 或產生無法被 finalize 驗證邏輯正確處理的
            # 狀態，一律拒絕。用路徑前綴比對（而非 ls-files --stage 查詢
            # target 本身，因為 submodule 內部的檔案不會出現在該查詢結果）。
            target_posix = target.path.replace("\\", "/").lstrip("/")
            for sub_path in submodule_paths:
                if target_posix == sub_path or target_posix.startswith(sub_path.rstrip("/") + "/"):
                    raise GitRepoError(
                        f"{target.path!r} 落在 git submodule {sub_path!r} 之內，"
                        "GitRepoConnector 不支援修改 submodule 內的檔案，已拒絕整個 session。"
                    )

    def begin_patch_session(self, plan) -> None:
        """開始一輪修復：確認 working tree 乾淨、確認 target 都不是被
        .gitignore 忽略的路徑、搶佔 session lock、建立新 branch。必須在
        任何 write_file() 呼叫之前呼叫這個方法。

        session marker（同時作為簡易 repo-level lock）在建立分支之前就
        先原子性地寫入：這樣若有另一個程序同時搶到 lock，這裡會提早失敗，
        不會留下一個已建立、卻沒有對應 session 記錄的 branch 需要清理。
        """
        if self._session_branch is not None:
            raise GitRepoError("已經有一個進行中的 patch session，不支援疊加多次 apply。")

        if not self._is_working_tree_clean():
            raise DirtyWorkingTreeError(
                "working tree 有未提交的變更，GitRepoConnector 要求乾淨的 working tree "
                "才能安全地建立修復用的新 branch。請先 commit 或 stash 現有變更。"
            )

        self._reject_unsafe_targets(plan)

        original_branch = self._current_branch()
        base_commit_result = self._git("rev-parse", "HEAD")
        if base_commit_result.returncode != 0:
            raise GitRepoError(f"無法取得目前 commit：{base_commit_result.stderr.strip()}")
        base_commit = base_commit_result.stdout.strip()

        branch_name = f"seo-advisor/fix-{_slugify(plan.finding_id)}"
        _validate_branch_name(self.root, branch_name)

        existing = self._git("show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}")
        if existing.returncode == 0:
            raise BranchAlreadyExistsError(
                f"分支 {branch_name!r} 已經存在，為避免覆蓋或混用先前的修復嘗試，拒絕重用。"
                f"若先前的分支已經沒用（例如 PR 已關閉/合併），請先手動刪除："
                f"`git branch -D {branch_name}`，再重新執行；"
                "若先前的分支仍在使用中，代表這個問題已經有進行中的修復，不需要重複產生。"
            )

        # 先搶 lock，成功後才建立分支：若搶不到 lock 就提早失敗，不會有
        # 「分支建好了但沒對應 session 記錄」需要額外清理的中間狀態。
        self._session_branch = branch_name
        self._session_base_commit = base_commit
        self._session_original_branch = original_branch
        self._session_targets = [target.path for target in plan.targets]
        try:
            self._write_session_marker(plan)
        except Exception:
            self._session_branch = None
            self._session_base_commit = None
            self._session_original_branch = None
            self._session_targets = []
            raise

        switch_result = self._git("switch", "-c", branch_name)
        if switch_result.returncode != 0:
            self._clear_session_marker()
            self._session_branch = None
            self._session_base_commit = None
            self._session_original_branch = None
            self._session_targets = []
            raise GitRepoError(f"建立分支 {branch_name!r} 失敗：{switch_result.stderr.strip()}")

    def finalize_patch_session(self, plan) -> GitPatchResult:
        """把這次 session 寫入的所有 target 加入 staging 並 commit。"""
        if self._session_branch is None:
            raise GitRepoError("尚未呼叫 begin_patch_session()，無法 finalize。")

        add_result = self._git("add", "--", *self._session_targets)
        if add_result.returncode != 0:
            self.abort_patch_session(plan)
            raise GitRepoError(f"git add 失敗：{add_result.stderr.strip()}")

        # 用 -z 以 NUL 分隔輸出，避免非 ASCII/特殊字元路徑在一般文字模式下
        # 被 core.quotePath 等設定影響、或含換行字元的檔名被誤判成多行。
        staged_result = self._git("diff", "--name-only", "-z", "--cached")
        staged_paths = {p for p in staged_result.stdout.split("\0") if p}
        expected_paths = {p.replace("\\", "/") for p in self._session_targets}
        if staged_paths != expected_paths:
            self.abort_patch_session(plan)
            raise GitRepoError(
                f"暫存區內容與預期的修復目標不符（預期 {sorted(expected_paths)}，"
                f"實際暫存 {sorted(staged_paths)}），為安全起見已中止並還原，不予提交。"
            )

        commit_message = (
            f"fix(seo): apply {plan.finding_id}\n\n"
            f"Plan: {plan.plan_id}\n"
            f"Finding: {plan.finding_id}\n"
            f"Source: Open SEO Advisor Engineer Mode"
        )
        commit_result = self._git("commit", "-m", commit_message)
        if commit_result.returncode != 0:
            self.abort_patch_session(plan)
            raise GitRepoError(f"git commit 失敗：{commit_result.stderr.strip()}")

        commit_sha = self._git("rev-parse", "HEAD").stdout.strip()

        result = GitPatchResult(
            plan_id=plan.plan_id,
            branch=self._session_branch,
            base_commit=self._session_base_commit,
            commit_sha=commit_sha,
            committed_paths=list(self._session_targets),
        )
        self._session_branch = None
        self._session_base_commit = None
        self._session_original_branch = None
        self._session_targets = []
        self._clear_session_marker()
        return result

    def abort_patch_session(self, plan) -> None:
        """中止這次 session：重設新 branch 到套用前的狀態、切回原本的
        branch、刪除這個新 branch。只在「這個 branch 是本 session 剛建立」
        的前提下執行，不會影響使用者原本就存在的任何 branch。
        """
        if self._session_branch is None:
            return

        branch_to_remove = self._session_branch
        original_branch = self._session_original_branch
        base_commit = self._session_base_commit

        self._git("reset", "--hard", base_commit)
        if original_branch:
            self._git("switch", original_branch)
        if branch_to_remove:
            self._git("branch", "-D", branch_to_remove)

        self._session_branch = None
        self._session_base_commit = None
        self._session_original_branch = None
        self._session_targets = []
        self._clear_session_marker()


def _slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return slug[:40] or "finding"
