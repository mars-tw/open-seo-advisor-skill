"""Open SEO Advisor CLI 入口。

新手用法（不需要記任何參數）：
    seo-advisor
    seo-advisor start

進階用法：
    seo-advisor audit consultant --url example.com --out ./report
    seo-advisor audit consultant --source ./my-site --out ./report
    seo-advisor demo

任何指令加上 --debug 都會在發生錯誤時顯示完整技術細節（Python traceback），
預設情況下只會顯示人話說明與建議的下一步，避免嚇到不熟悉程式的使用者。
"""

from __future__ import annotations

import typer
from rich.console import Console

from seo_advisor.demo import run_demo_scan
from seo_advisor.errors import translate_exception
from seo_advisor.models import Mode
from seo_advisor.router import ModeNotImplementedError, UnknownModeError, ensure_implemented, resolve_mode
from seo_advisor.scan_runner import ScanOutcome, run_consultant_scan
from seo_advisor.wizard import run_wizard

app = typer.Typer(
    help="Open SEO Advisor - 開源全域 SEO 顧問技能 CLI。不知道從哪裡開始？直接輸入 seo-advisor 即可。",
    invoke_without_command=True,
)
audit_app = typer.Typer(help="執行 SEO 健檢（顧問模式等，進階用法）")
app.add_typer(audit_app, name="audit")

console = Console()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        run_wizard(console)


@app.command("start")
def start(
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """新手推薦入口：用問答方式引導完成第一次 SEO 健檢。"""
    run_wizard(console, debug=debug)


@app.command("demo")
def demo(
    out: str = typer.Option("./seo-demo-report", "--out", help="報告輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """不需要輸入任何網址，直接看一份範例 SEO 健檢報告長什麼樣子。"""
    console.print("[cyan]這是示範模式，會使用內建的範例網站資料，不會真的連到網路上的任何網站。[/cyan]")
    _run_scan(lambda progress: run_demo_scan(out_dir=out, on_progress=progress), debug=debug)


@audit_app.command("consultant")
def audit_consultant(
    url: str = typer.Option(None, "--url", help="要檢查的網站 URL（與 --source 擇一，可省略 https://）"),
    source: str = typer.Option(None, "--source", help="本地原始碼包或目錄路徑（與 --url 擇一）"),
    out: str = typer.Option("./report", "--out", help="報告輸出目錄"),
    max_urls: int = typer.Option(200, "--max-urls", help="最多爬取的 URL 數量"),
    max_depth: int = typer.Option(6, "--max-depth", help="最大爬取深度"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """執行顧問模式（Consultant Mode）全站 SEO 健檢（進階指令，新手建議改用 `seo-advisor start`）。"""

    ensure_implemented(Mode.CONSULTANT)

    if not url and not source:
        console.print("[red]錯誤：必須提供 --url 或 --source 其中之一。[/red]")
        console.print("[dim]不確定怎麼用嗎？直接執行 `seo-advisor start` 會用問答方式引導你。[/dim]")
        raise typer.Exit(code=1)
    if url and source:
        console.print("[red]錯誤：--url 與 --source 不可同時提供，請擇一使用。[/red]")
        raise typer.Exit(code=1)

    _run_scan(
        lambda progress: run_consultant_scan(
            url=url, source=source, out_dir=out, max_urls=max_urls, max_depth=max_depth, on_progress=progress
        ),
        debug=debug,
    )


@app.command("mode")
def show_mode_status(name: str) -> None:
    """查詢指定模式的實作狀態（給想知道 Engineer/Security 等模式進度的使用者）。"""
    try:
        mode = resolve_mode(name)
    except UnknownModeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    try:
        ensure_implemented(mode)
        console.print(f"[green]模式 {mode.value} 已實作，可直接使用。[/green]")
    except ModeNotImplementedError as exc:
        console.print(f"[yellow]{exc}[/yellow]")


def _run_scan(scan_fn, *, debug: bool) -> None:
    try:
        outcome: ScanOutcome = scan_fn(lambda msg: console.print(f"[dim]{msg}[/dim]"))
    except Exception as exc:  # noqa: BLE001 - 統一在 CLI 邊界把例外轉成人話說明
        if debug:
            raise
        friendly = translate_exception(exc)
        console.print(f"[red]{friendly.render()}[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[bold green]完成！健康分數：{outcome.report.site_health_score:.0f}/100，"
        f"共 {len(outcome.report.findings)} 項發現。[/bold green]"
    )
    console.print(f"給非技術人員看的懶人包：{outcome.beginner_path}")
    console.print(f"完整技術報告：{outcome.technical_path}")
    console.print(f"機器可讀資料：{outcome.json_path}")


if __name__ == "__main__":
    app()
