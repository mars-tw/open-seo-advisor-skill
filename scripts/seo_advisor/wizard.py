"""互動式精靈：給不熟悉命令列參數的使用者，用問答方式完成掃描。

執行 `seo-advisor` 或 `seo-advisor start` 且未帶任何參數時觸發。
所有實際邏輯都委派給 scan_runner / demo，這裡只負責「問問題、印結果」。
"""

from __future__ import annotations

from rich.console import Console
from rich.prompt import Prompt

from seo_advisor.autopilot.models import AutoTask
from seo_advisor.autopilot.runner import run_autopilot
from seo_advisor.demo import run_demo_scan
from seo_advisor.errors import translate_exception
from seo_advisor.scan_runner import ScanOutcome, run_consultant_scan


def run_wizard(console: Console, *, debug: bool = False) -> None:
    console.print()
    console.print("[bold cyan]歡迎使用 Open SEO Advisor[/bold cyan]")
    console.print("全程用問答方式進行，不需要記任何指令。不確定選哪個？直接選 1 就好。")
    console.print()

    console.print("請問你想做什麼？")
    console.print("  [bold]1[/bold] - 一鍵全自動（給我一個網址，剩下交給我，最推薦）")
    console.print("  [bold]2[/bold] - 只做 SEO 健檢（掃描一個真實網站）")
    console.print("  [bold]3[/bold] - 掃描本機資料夾裡的網站原始碼")
    console.print("  [bold]4[/bold] - 先看一份範例報告（不需要輸入網址）")
    console.print()

    choice = Prompt.ask("請輸入數字", choices=["1", "2", "3", "4"], default="1")

    if choice == "1":
        target = Prompt.ask("請輸入你的網站網址，或一句想達成的目標")
        out_dir = Prompt.ask("報告要存到哪個資料夾？", default="./auto-report")
        _run_autopilot_and_report(console, target, out_dir, debug=debug)
        return

    if choice == "4":
        _run_and_report(console, lambda progress: run_demo_scan(out_dir="./seo-demo-report", on_progress=progress), debug=debug)
        return

    if choice == "2":
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


def _run_autopilot_and_report(console: Console, target: str, out_dir: str, *, debug: bool) -> None:
    console.print()
    console.print("[dim]交給我，正在自動出動各領域專家分析……全程免費、不會花任何錢。[/dim]")
    try:
        outcome = run_autopilot(
            AutoTask(target=target),
            out_dir=out_dir,
            consented=False,
            on_progress=lambda msg: console.print(f"  [dim]{msg}[/dim]"),
        )
    except Exception as exc:  # noqa: BLE001 - 攔截所有例外轉成人話
        console.print()
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        return

    console.print()
    console.print("[bold green]完成！一鍵顧問已幫你分析完畢。[/bold green]")
    console.print()
    console.print("[bold]先看這份最好懂的：[/bold]")
    console.print(f"  給你的白話懶人包：{outcome.beginner_path}")
    console.print(f"  會不會花錢的明細：{outcome.cost_estimate_path}")
    console.print(f"  完整報告（可交給團隊）：{outcome.report_path}")
    console.print()
    console.print("[dim]這次只做了免費的分析。若要讓系統自動執行安全動作，"
                  "可用 seo-advisor auto <網址> --approve 完成一次同意。[/dim]")


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
