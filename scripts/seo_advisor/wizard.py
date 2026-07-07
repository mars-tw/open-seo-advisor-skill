"""互動式精靈：給不熟悉命令列參數的使用者，用問答方式完成掃描。

執行 `seo-advisor` 或 `seo-advisor start` 且未帶任何參數時觸發。
所有實際邏輯都委派給 scan_runner / demo，這裡只負責「問問題、印結果」。
"""

from __future__ import annotations

from rich.console import Console
from rich.prompt import Prompt

from seo_advisor.autopilot.models import AutoTask
from seo_advisor.autopilot.runner import run_autopilot
from seo_advisor.errors import translate_exception


def run_wizard(console: Console, *, debug: bool = False) -> None:
    console.print()
    console.print("[bold cyan]歡迎使用 Open SEO Advisor[/bold cyan]")
    console.print("全程用問答方式進行，不需要記任何指令。不確定選哪個？直接選 1 就好。")
    console.print()

    # 新手預設路徑：只問一件事——你的網址。剩下全自動。沒有網址就先看範例。
    console.print("請貼上你的網站網址就好（例如 example.com）。")
    console.print("[dim]還沒有網站、想先看看範例？直接按 Enter 就好。[/dim]")
    target = Prompt.ask("你的網址", default="").strip()

    if not target:
        console.print("[cyan]好，先帶你看一份範例報告（不需要網址、不花錢）。[/cyan]")
        _run_autopilot_and_report(console, "https://example.com", "./auto-demo", debug=debug, mock=True)
        return

    out_dir = Prompt.ask("報告要存到哪個資料夾？", default="./auto-report")
    _run_autopilot_and_report(console, target, out_dir, debug=debug)


def _run_autopilot_and_report(
    console: Console, target: str, out_dir: str, *, debug: bool, mock: bool = False
) -> None:
    console.print()
    console.print("[dim]交給我，正在自動出動各領域專家分析……預設只做分析、不花錢、不改動你的網站。[/dim]")
    try:
        outcome = run_autopilot(
            AutoTask(target=target, mock=mock),
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
    console.print("[bold green]完成！一鍵顧問已幫你分析完畢。你不需要記任何指令。[/bold green]")
    console.print()
    console.print("[bold]打開這份最好懂的就對了：[/bold]")
    console.print(f"  {outcome.beginner_path}")
    console.print()
    console.print("[dim]看不懂名詞？docs/glossary-for-beginners.md 有白話對照表。[/dim]")
