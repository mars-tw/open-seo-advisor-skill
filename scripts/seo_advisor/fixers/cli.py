"""Engineer Mode 的 CLI subapp（seo-advisor fix ...）。

安全設計：
- 預設永遠 dry-run（只產出 fix-plan.md/json，不寫入任何檔案）。
- 真寫入需要同時滿足 `--apply` 與 `--confirm "APPLY <plan_id>"`（plan_id
  在 dry-run 輸出裡看得到，逼迫使用者確認的是「這一份」計畫，不是隨便
  一句固定通關密語）。
- 只支援本地原始碼包/目錄（--source）。網址/CMS API 的寫入能力屬於
  之後批次（SSHConnector/WordPressAPIConnector）的範圍，這裡不提供
  --url 選項，避免誤以為能直接修改線上網站。
- --rollback 走同樣的二次確認機制，且絕不覆蓋使用者套用後又手動修改過的
  檔案（見 fixers/rollback.py）。
- --write-mode direct（預設）直接修改 --source 目錄裡的檔案；
  --write-mode git-branch 改成在該目錄（須為已存在的 git repo）建立新
  branch + commit，不觸碰目前 working tree，方便直接 push 開 PR review。
  git-branch 模式要求 working tree 完全乾淨，否則會拒絕執行（見
  connectors/git_repo.py 的 GitRepoConnector）。
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from seo_advisor.connectors.git_repo import GitRepoConnector
from seo_advisor.connectors.local_archive import LocalArchiveConnector
from seo_advisor.crawler import crawl_site
from seo_advisor.errors import translate_exception
from seo_advisor.fixers import rollback as rollback_module
from seo_advisor.fixers import runner
from seo_advisor.fixers.hreflang_generator import build_hreflang_html_plan
from seo_advisor.fixers.hreflang_map import InvalidLanguageMapError, load_language_map
from seo_advisor.fixers.hreflang_sitemap import build_hreflang_sitemap_plan
from seo_advisor.fixers.safety import build_apply_confirmation, build_rollback_confirmation, verify_confirmation
from seo_advisor.models import Finding, SafetyPolicy

fix_app = typer.Typer(help="Engineer Mode：把顧問報告的問題轉成可審核的修復計畫，確認後才寫入")
console = Console()


def _load_findings(source: str, from_report: str | None, finding_id: str | None) -> tuple[list[Finding], object]:
    """回傳 (findings, crawl_result)。若沒有 --from-report，就地對 source 跑一次快速掃描。"""
    connector = LocalArchiveConnector(source)
    if from_report:
        report_data = json.loads(Path(from_report).read_text(encoding="utf-8"))
        findings = [Finding(**f) for f in report_data["findings"]]
    else:
        findings = []

    crawl_result = crawl_site(connector, seed_url="/", max_urls=200, max_depth=6, fetched_at="")

    if not from_report:
        from seo_advisor.analyzers.technical import analyze_technical_seo

        findings = analyze_technical_seo(crawl_result, seed_url="/")

    if finding_id:
        findings = [f for f in findings if f.id == finding_id]

    return findings, crawl_result


# 這幾種修復類型的內容必須是絕對 URL 才有實質意義（robots.txt 的 Sitemap
# 宣告、sitemap.xml 的 <loc>），本地掃描沒有真實網域可用，因此沒提供
# --site-url 時只能猜出相對路徑，必須明確警告使用者這不是最終正確內容。
_NEEDS_SITE_URL_FIX_TYPES = {"robots_txt", "sitemap"}


@fix_app.command("engineer")
def engineer(
    source: str = typer.Option(..., "--source", help="本地原始碼包目錄或 zip 檔路徑"),
    finding_id: str = typer.Option(None, "--finding-id", help="只修復指定的 Finding ID（不指定則列出所有可修復項目）"),
    from_report: str = typer.Option(None, "--from-report", help="顧問報告 JSON 路徑（不指定則就地跑一次快速掃描）"),
    site_url: str = typer.Option(
        None, "--site-url", help="正式站台網址（例如 https://example.com），用於產生 sitemap/robots.txt 裡的絕對 URL"
    ),
    write_mode: str = typer.Option(
        "direct", "--write-mode",
        help='寫入方式："direct"（預設，直接改 --source 目錄）或 "git-branch"'
        "（在 --source 這個 git repo 建立新分支+commit，不動目前 working tree，"
        "要求 working tree 完全乾淨）",
    ),
    apply: bool = typer.Option(False, "--apply", help="真的寫入檔案（預設為 dry-run 預覽）"),
    confirm: str = typer.Option(None, "--confirm", help='套用時需要輸入 "APPLY <plan_id>"（plan_id 見 dry-run 輸出）'),
    out: str = typer.Option("./fix-plan", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """產出修復計畫（預設 dry-run）；加 --apply --confirm 才會真的寫入檔案。"""
    try:
        if write_mode not in ("direct", "git-branch"):
            console.print(f'[red]--write-mode 只接受 "direct" 或 "git-branch"，收到 {write_mode!r}。[/red]')
            raise typer.Exit(code=1)

        findings, crawl_result = _load_findings(source, from_report, finding_id)
        fixable = runner.list_fixable_findings(findings)

        if not finding_id:
            if not fixable:
                console.print("[yellow]目前沒有找到 Engineer Mode 能自動修復的問題。[/yellow]")
                raise typer.Exit(code=0)
            console.print("[bold]可自動修復的項目：[/bold]")
            for f in fixable:
                console.print(f"  - {f.id}：{f.title}")
            console.print("\n加上 --finding-id <ID> 產出該項目的修復計畫。")
            raise typer.Exit(code=0)

        if not fixable:
            console.print(f"[red]{finding_id} 目前沒有對應的自動修復邏輯，或找不到這個 Finding。[/red]")
            raise typer.Exit(code=1)

        target_finding = fixable[0]
        write_policy = SafetyPolicy(
            dry_run=not apply, allowed_capabilities={"read_urls", "read_files", "write_files"}
        )
        if write_mode == "git-branch":
            connector = GitRepoConnector(source, policy=write_policy)
        else:
            connector = LocalArchiveConnector(source, policy=write_policy)

        fixer_module = runner.find_fixer(target_finding)
        if fixer_module.__name__.rsplit(".", 1)[-1] in ("robots", "sitemap") and not site_url:
            console.print(
                "[yellow]警告：未提供 --site-url，robots.txt/sitemap.xml 裡的網址將只是相對路徑，"
                "不是正式可用的絕對網址。強烈建議加上 --site-url https://你的正式網域 重新產生。[/yellow]"
            )

        seed_for_plan = site_url or "/"
        plan = runner.build_plan(target_finding, connector=connector, crawl_result=crawl_result, seed_url=seed_for_plan)

        out_path = Path(out)
        out_path.mkdir(parents=True, exist_ok=True)
        (out_path / "fix-plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        _render_plan_markdown(plan, out_path / "fix-plan.md")

        if plan.plan_only:
            console.print(f"[bold]建議（需人工處理，無法自動套用）：{plan.plan_id}[/bold]")
            console.print(plan.summary)
            for warning in plan.warnings:
                console.print(f"[yellow]警告：{warning}[/yellow]")
            console.print("\n[bold]建議步驟：[/bold]")
            for step in plan.suggested_actions:
                console.print(f"  - {step}")
            console.print(
                "\n[cyan]這個項目超出 Engineer Mode 可以安全自動寫入的範圍，"
                "已產出建議步驟供人工處理，不會提供 --apply 套用選項。[/cyan]"
            )
            raise typer.Exit(code=0)

        console.print(f"[bold]修復計畫：{plan.plan_id}[/bold]（風險等級：{plan.risk_level}）")
        console.print(plan.summary)
        for warning in plan.warnings:
            console.print(f"[yellow]警告：{warning}[/yellow]")
        for target in plan.targets:
            console.print(f"\n[dim]--- {target.path} ---[/dim]")
            console.print(target.diff_preview or "（無文字 diff）")

        if not apply:
            write_mode_flag = f" --write-mode {write_mode}" if write_mode != "direct" else ""
            console.print(
                f"\n[cyan]這是 dry-run 預覽，尚未寫入任何檔案。[/cyan]\n"
                f"確認無誤後執行：\n"
                f'  seo-advisor fix engineer --source {source} --finding-id {target_finding.id}'
                f'{write_mode_flag} --apply --confirm "{build_apply_confirmation(plan.plan_id)}"'
            )
            raise typer.Exit(code=0)

        expected = build_apply_confirmation(plan.plan_id)
        if not confirm or not verify_confirmation(confirm, expected):
            console.print(
                f'[red]確認字串不符或未提供。請加上 --confirm "{expected}" 才會真的寫入。[/red]'
            )
            raise typer.Exit(code=1)

        result = runner.apply_plan(plan, connector=connector)
        (out_path / "fix-result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")

        if result.applied:
            if write_mode == "git-branch":
                console.print("[bold green]已套用！變更已 commit 到新分支。[/bold green]")
                for note in result.validation_notes:
                    console.print(note)
            else:
                console.print(f"[bold green]已套用！寫入 {len(result.written_paths)} 個檔案。[/bold green]")
                console.print(f"備份位置：{result.backup_id}")
                console.print(
                    f"若需回滾：seo-advisor fix rollback --source {source} --backup {result.backup_id}"
                )
        else:
            console.print("[red]套用中斷，未完全成功。[/red]")
            for note in result.validation_notes:
                console.print(f"[red]{note}[/red]")
            raise typer.Exit(code=1)

    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)


def _load_hreflang_pages(connector, hreflang_map) -> dict[str, str]:
    """讀取語言對照表所有 cluster.targets 指到的檔案內容，供 HTML generator
    使用。找不到的檔案不在這裡報錯——留給 generator 自己判斷並記錄警告，
    讓整個流程能盡量處理完其他仍然有效的 cluster，而不是一個檔案讀取失敗
    就中斷整批。
    """
    pages: dict[str, str] = {}
    for cluster in hreflang_map.clusters:
        for rel_path in cluster.targets.values():
            if rel_path in pages:
                continue
            try:
                pages[rel_path] = connector.read_file(rel_path).decode("utf-8", errors="replace")
            except (FileNotFoundError, ValueError, OSError):
                continue
    return pages


@fix_app.command("hreflang-html")
def hreflang_html(
    source: str = typer.Option(..., "--source", help="本地原始碼包目錄或 zip 檔路徑"),
    map_file: str = typer.Option(..., "--map", help="語言對照表 JSON 檔案路徑（見 docs/modes.md#engineer-mode）"),
    write_mode: str = typer.Option(
        "direct", "--write-mode", help='寫入方式："direct"（預設）或 "git-branch"（見 fix engineer 說明）'
    ),
    apply: bool = typer.Option(False, "--apply", help="真的寫入檔案（預設為 dry-run 預覽）"),
    confirm: str = typer.Option(None, "--confirm", help='套用時需要輸入 "APPLY <plan_id>"（plan_id 見 dry-run 輸出）'),
    out: str = typer.Option("./fix-plan", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """依語言對照表在指定頁面插入 hreflang 標籤（預設 dry-run）。

    語言對照表由使用者提供、視為權威輸入，工具不會驗證其業務正確性
    （例如網址是否真的對應正確語言版本），只負責安全地產生/套用標籤。
    """
    try:
        if write_mode not in ("direct", "git-branch"):
            console.print(f'[red]--write-mode 只接受 "direct" 或 "git-branch"，收到 {write_mode!r}。[/red]')
            raise typer.Exit(code=1)

        try:
            hreflang_map = load_language_map(map_file)
        except InvalidLanguageMapError as exc:
            console.print(f"[red]語言對照表不合法：{exc}[/red]")
            raise typer.Exit(code=1)

        write_policy = SafetyPolicy(
            dry_run=not apply, allowed_capabilities={"read_urls", "read_files", "write_files"}
        )
        if write_mode == "git-branch":
            connector = GitRepoConnector(source, policy=write_policy)
        else:
            connector = LocalArchiveConnector(source, policy=write_policy)

        pages = _load_hreflang_pages(connector, hreflang_map)
        plan = build_hreflang_html_plan(hreflang_map, pages=pages)

        out_path = Path(out)
        out_path.mkdir(parents=True, exist_ok=True)
        (out_path / "fix-plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        _render_plan_markdown(plan, out_path / "fix-plan.md")

        if plan.plan_only:
            console.print(f"[bold]建議（需人工處理，無法自動套用）：{plan.plan_id}[/bold]")
            console.print(plan.summary)
            for warning in plan.warnings:
                console.print(f"[yellow]警告：{warning}[/yellow]")
            console.print("\n[bold]建議步驟：[/bold]")
            for step in plan.suggested_actions:
                console.print(f"  - {step}")
            raise typer.Exit(code=0)

        console.print(f"[bold]修復計畫：{plan.plan_id}[/bold]（風險等級：{plan.risk_level}）")
        console.print(plan.summary)
        for warning in plan.warnings:
            console.print(f"[yellow]警告：{warning}[/yellow]")
        for target in plan.targets:
            console.print(f"\n[dim]--- {target.path} ---[/dim]")
            console.print(target.diff_preview or "（無文字 diff）")

        if not apply:
            write_mode_flag = f" --write-mode {write_mode}" if write_mode != "direct" else ""
            console.print(
                f"\n[cyan]這是 dry-run 預覽，尚未寫入任何檔案。[/cyan]\n"
                f"確認無誤後執行：\n"
                f"  seo-advisor fix hreflang-html --source {source} --map {map_file}"
                f'{write_mode_flag} --apply --confirm "{build_apply_confirmation(plan.plan_id)}"'
            )
            raise typer.Exit(code=0)

        expected = build_apply_confirmation(plan.plan_id)
        if not confirm or not verify_confirmation(confirm, expected):
            console.print(f'[red]確認字串不符或未提供。請加上 --confirm "{expected}" 才會真的寫入。[/red]')
            raise typer.Exit(code=1)

        result = runner.apply_plan(plan, connector=connector)
        (out_path / "fix-result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")

        if result.applied:
            if write_mode == "git-branch":
                console.print("[bold green]已套用！變更已 commit 到新分支。[/bold green]")
                for note in result.validation_notes:
                    console.print(note)
            else:
                console.print(f"[bold green]已套用！寫入 {len(result.written_paths)} 個檔案。[/bold green]")
                console.print(f"備份位置：{result.backup_id}")
                console.print(f"若需回滾：seo-advisor fix rollback --source {source} --backup {result.backup_id}")
        else:
            console.print("[red]套用中斷，未完全成功。[/red]")
            for note in result.validation_notes:
                console.print(f"[red]{note}[/red]")
            raise typer.Exit(code=1)

    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)


@fix_app.command("hreflang-sitemap")
def hreflang_sitemap(
    source: str = typer.Option(..., "--source", help="本地原始碼包目錄或 zip 檔路徑"),
    map_file: str = typer.Option(..., "--map", help="語言對照表 JSON 檔案路徑"),
    sitemap_path: str = typer.Option("sitemap.xml", "--sitemap", help="要修改（或建立）的 sitemap 檔案路徑"),
    write_mode: str = typer.Option(
        "direct", "--write-mode", help='寫入方式："direct"（預設）或 "git-branch"（見 fix engineer 說明）'
    ),
    apply: bool = typer.Option(False, "--apply", help="真的寫入檔案（預設為 dry-run 預覽）"),
    confirm: str = typer.Option(None, "--confirm", help='套用時需要輸入 "APPLY <plan_id>"（plan_id 見 dry-run 輸出）'),
    out: str = typer.Option("./fix-plan", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """依語言對照表在 sitemap.xml 加入 xhtml:link hreflang 條目（預設 dry-run）。"""
    try:
        if write_mode not in ("direct", "git-branch"):
            console.print(f'[red]--write-mode 只接受 "direct" 或 "git-branch"，收到 {write_mode!r}。[/red]')
            raise typer.Exit(code=1)

        try:
            hreflang_map = load_language_map(map_file)
        except InvalidLanguageMapError as exc:
            console.print(f"[red]語言對照表不合法：{exc}[/red]")
            raise typer.Exit(code=1)

        write_policy = SafetyPolicy(
            dry_run=not apply, allowed_capabilities={"read_urls", "read_files", "write_files"}
        )
        if write_mode == "git-branch":
            connector = GitRepoConnector(source, policy=write_policy)
        else:
            connector = LocalArchiveConnector(source, policy=write_policy)

        try:
            current_xml = connector.read_file(sitemap_path).decode("utf-8", errors="replace")
        except (FileNotFoundError, ValueError, OSError):
            current_xml = None

        plan = build_hreflang_sitemap_plan(hreflang_map, sitemap_path=sitemap_path, current_sitemap_xml=current_xml)

        out_path = Path(out)
        out_path.mkdir(parents=True, exist_ok=True)
        (out_path / "fix-plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        _render_plan_markdown(plan, out_path / "fix-plan.md")

        if plan.plan_only:
            console.print(f"[bold]建議（需人工處理，無法自動套用）：{plan.plan_id}[/bold]")
            console.print(plan.summary)
            for warning in plan.warnings:
                console.print(f"[yellow]警告：{warning}[/yellow]")
            console.print("\n[bold]建議步驟：[/bold]")
            for step in plan.suggested_actions:
                console.print(f"  - {step}")
            raise typer.Exit(code=0)

        console.print(f"[bold]修復計畫：{plan.plan_id}[/bold]（風險等級：{plan.risk_level}）")
        console.print(plan.summary)
        for target in plan.targets:
            console.print(f"\n[dim]--- {target.path} ---[/dim]")
            console.print(target.diff_preview or "（無文字 diff）")

        if not apply:
            write_mode_flag = f" --write-mode {write_mode}" if write_mode != "direct" else ""
            console.print(
                f"\n[cyan]這是 dry-run 預覽，尚未寫入任何檔案。[/cyan]\n"
                f"確認無誤後執行：\n"
                f"  seo-advisor fix hreflang-sitemap --source {source} --map {map_file} --sitemap {sitemap_path}"
                f'{write_mode_flag} --apply --confirm "{build_apply_confirmation(plan.plan_id)}"'
            )
            raise typer.Exit(code=0)

        expected = build_apply_confirmation(plan.plan_id)
        if not confirm or not verify_confirmation(confirm, expected):
            console.print(f'[red]確認字串不符或未提供。請加上 --confirm "{expected}" 才會真的寫入。[/red]')
            raise typer.Exit(code=1)

        result = runner.apply_plan(plan, connector=connector)
        (out_path / "fix-result.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")

        if result.applied:
            if write_mode == "git-branch":
                console.print("[bold green]已套用！變更已 commit 到新分支。[/bold green]")
                for note in result.validation_notes:
                    console.print(note)
            else:
                console.print(f"[bold green]已套用！寫入 {len(result.written_paths)} 個檔案。[/bold green]")
                console.print(f"備份位置：{result.backup_id}")
                console.print(f"若需回滾：seo-advisor fix rollback --source {source} --backup {result.backup_id}")
        else:
            console.print("[red]套用中斷，未完全成功。[/red]")
            for note in result.validation_notes:
                console.print(f"[red]{note}[/red]")
            raise typer.Exit(code=1)

    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)


@fix_app.command("rollback")
def rollback(
    source: str = typer.Option(..., "--source", help="本地原始碼包目錄或 zip 檔路徑"),
    backup: str = typer.Option(..., "--backup", help="備份目錄路徑（見 fix engineer 套用後輸出的備份位置）"),
    apply: bool = typer.Option(False, "--apply", help="真的還原檔案（預設為 dry-run 預覽）"),
    confirm: str = typer.Option(None, "--confirm", help='還原時需要輸入 "ROLLBACK <backup_id>"'),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """從備份還原檔案；不會覆蓋你在套用修復之後又手動編輯過的檔案。"""
    try:
        root = Path(source).resolve()
        backup_id = Path(backup).name

        safe_paths, skipped_paths = rollback_module.plan_rollback(backup, root=root)
        console.print(f"[bold]備份：{backup_id}[/bold]")
        console.print(f"可安全還原：{safe_paths or '（無）'}")
        if skipped_paths:
            console.print(
                f"[yellow]將跳過（可能已被手動修改過）：{skipped_paths}[/yellow]"
            )

        if not apply:
            console.print(
                f"\n[cyan]這是 dry-run 預覽，尚未還原任何檔案。[/cyan]\n"
                f"確認無誤後執行：\n"
                f'  seo-advisor fix rollback --source {source} --backup {backup} '
                f'--apply --confirm "{build_rollback_confirmation(backup_id)}"'
            )
            raise typer.Exit(code=0)

        expected = build_rollback_confirmation(backup_id)
        if not confirm or not verify_confirmation(confirm, expected):
            console.print(
                f'[red]確認字串不符或未提供。請加上 --confirm "{expected}" 才會真的還原。[/red]'
            )
            raise typer.Exit(code=1)

        result = rollback_module.rollback(backup, root=root)
        if result.restored:
            console.print(f"[bold green]已還原 {len(result.restored_paths)} 個檔案。[/bold green]")
        else:
            console.print("[yellow]沒有檔案被還原。[/yellow]")
        for note in result.notes:
            console.print(f"[yellow]{note}[/yellow]")

    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)


def _render_plan_markdown(plan, path: Path) -> None:
    title = "建議（需人工處理，無法自動套用）" if plan.plan_only else "修復計畫"
    lines = [
        f"# {title}：{plan.plan_id}",
        "",
        f"- Finding ID：{plan.finding_id}",
        f"- 修復類型：{plan.fix_type}",
        f"- 風險等級：{plan.risk_level}",
        f"- 是否可自動套用：{'否（plan_only）' if plan.plan_only else '是'}",
        "",
        f"## 摘要\n\n{plan.summary}",
    ]
    if plan.warnings:
        lines.append("\n## 警告\n")
        lines.extend(f"- {w}" for w in plan.warnings)
    if plan.plan_only:
        lines.append("\n## 建議步驟\n")
        lines.extend(f"- {step}" for step in plan.suggested_actions)
    else:
        lines.append("\n## 變更內容\n")
        for target in plan.targets:
            lines.append(f"### {target.path}\n\n```diff\n{target.diff_preview}\n```\n")
    path.write_text("\n".join(lines), encoding="utf-8")
