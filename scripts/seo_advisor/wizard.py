"""互動式精靈：給不熟悉命令列參數的使用者，用問答方式完成掃描。

執行 `seo-advisor` 或 `seo-advisor start` 且未帶任何參數時觸發。
所有實際邏輯都委派給 scan_runner / demo，這裡只負責「問問題、印結果」。
"""

from __future__ import annotations

from rich.console import Console
from rich.prompt import Prompt

from seo_advisor.demo import run_demo_scan
from seo_advisor.errors import translate_exception
from seo_advisor.scan_runner import ScanOutcome, run_consultant_scan


def run_wizard(console: Console, *, debug: bool = False) -> None:
    console.print()
    console.print("[bold cyan]歡迎使用 Open SEO Advisor[/bold cyan]")
    console.print("我會幫你檢查一個網站的 SEO 健康狀況，全程用問答方式進行，不需要記任何指令。")
    console.print()

    console.print("請問你想做什麼？")
    console.print("  [bold]1[/bold] - 掃描一個真實網站，產生 SEO 健檢報告")
    console.print("  [bold]2[/bold] - 掃描本機資料夾裡的網站原始碼")
    console.print("  [bold]3[/bold] - 先看一份範例報告（不需要輸入網址）")
    console.print()

    choice = Prompt.ask("請輸入數字", choices=["1", "2", "3"], default="3")

    if choice == "3":
        _run_and_report(console, lambda progress: run_demo_scan(out_dir="./seo-demo-report", on_progress=progress), debug=debug)
        return

    if choice == "1":
        raw_url = Prompt.ask("請輸入網站網址（例如 example.com）")
        out_dir = Prompt.ask("報告要存到哪個資料夾？", default="./seo-report")
        _run_and_report(
            console,
            lambda progress: run_consultant_scan(url=raw_url, source=None, out_dir=out_dir, on_progress=progress),
            debug=debug,
        )
        return

    folder = Prompt.ask("請輸入本機資料夾或 zip 檔的路徑")
    out_dir = Prompt.ask("報告要存到哪個資料夾？", default="./seo-report")
    _run_and_report(
        console,
        lambda progress: run_consultant_scan(url=None, source=folder, out_dir=out_dir, on_progress=progress),
        debug=debug,
    )


def _run_and_report(console: Console, scan_fn, *, debug: bool) -> None:
    console.print()
    try:
        outcome: ScanOutcome = scan_fn(lambda msg: console.print(f"  [dim]{msg}[/dim]"))
    except Exception as exc:  # noqa: BLE001 - 這裡刻意攔截所有例外轉成人話說明
        console.print()
        if debug:
            raise
        friendly = translate_exception(exc)
        console.print(f"[red]{friendly.render()}[/red]")
        return

    _print_success(console, outcome)


def _print_success(console: Console, outcome: ScanOutcome) -> None:
    console.print()
    console.print(
        f"[bold green]完成！網站健康分數：{outcome.report.site_health_score:.0f}/100"
        f"，共發現 {len(outcome.report.findings)} 項可改善之處。[/bold green]"
    )
    console.print()
    console.print("[bold]接下來你可以看：[/bold]")
    console.print(f"  給非技術人員看的懶人包：{outcome.beginner_path}")
    console.print(f"  給工程師/SEO 顧問看的完整技術報告：{outcome.technical_path}")
    console.print(f"  給程式或自動化流程用的資料：{outcome.json_path}")
    console.print()
    console.print("[dim]看不懂報告裡的名詞？可以查 docs/glossary-for-beginners.md 的白話對照表。[/dim]")
