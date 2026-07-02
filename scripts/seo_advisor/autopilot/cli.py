"""一鍵代操機器人的 CLI（seo-advisor auto ...）。

新手一個指令就能用：`seo-advisor auto <你的網址或目標>`。
- 不加 --approve：只跑免費分析、產出報告與成本明細，不執行任何花錢動作。
- 加 --approve：跑完分析後，顯示白話成本明細，要求輸入同意確認字串；
  同意後才執行白名單內的安全動作（本版真實花錢動作仍停在計畫）。
"""

from __future__ import annotations

import typer
from rich.console import Console

from seo_advisor.autopilot.models import AutoTask
from seo_advisor.autopilot.runner import run_autopilot
from seo_advisor.autopilot.safety import build_consent_phrase, verify_consent
from seo_advisor.errors import translate_exception

console = Console()


def _consent_flow(cost) -> bool:
    """顯示白話成本明細並收一次同意。回傳是否同意。"""
    console.print()
    console.print("[bold]如果你按同意，系統最多會做這些事：[/bold]")
    console.print()
    if not cost.items:
        console.print("這次沒有任何會花錢、寫入或發布的動作，可以安心執行。")
        return True
    for i, item in enumerate(cost.items, start=1):
        console.print(f"  {i}. {item.action_summary}")
        console.print(f"     - {item.user_facing_explanation}")
        console.print(f"     - 風險：{item.risk_level.value}｜可回滾：{'可以' if item.reversible else '不可'}")
    console.print()
    console.print(f"[cyan]{cost.plain_language_summary}[/cyan]")
    console.print()

    phrase = build_consent_phrase(cost.max_authorized_minor_units, cost.currency)
    console.print("若要授權自動執行，請「完整輸入」這句話（其他輸入都視為不同意）：")
    console.print(f"[bold yellow]{phrase}[/bold yellow]")
    try:
        user_input = typer.prompt("你的輸入")
    except (EOFError, KeyboardInterrupt):
        return False
    return verify_consent(user_input, phrase)


def auto(
    target: str = typer.Argument(..., help="你的網址，或一句想達成的目標"),
    industry: str = typer.Option(None, "--industry", help="行業（可省略）"),
    approve: bool = typer.Option(
        False, "--approve", help="跑完分析後進入同意流程，同意才執行安全動作"
    ),
    mock: bool = typer.Option(False, "--mock", help="強制示範模式（不呼叫任何真實 API）"),
    out: str = typer.Option("./auto-report", "--out", help="報告輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """一鍵專家顧問：一個指令自動分析並產出完整優化方案與白話報告。

    新手就這樣用：seo-advisor auto https://你的網站.com
    """
    task = AutoTask(target=target, industry=industry, mock=mock)

    # 先跑一次分析（尚未同意），拿到成本明細
    try:
        preview = run_autopilot(
            task, out_dir=out, consented=False, on_progress=lambda m: console.print(f"[dim]{m}[/dim]")
        )
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    consented = False
    if approve:
        consented = _consent_flow(preview.deliverable.cost_estimate)
        if consented:
            # 以同意狀態重跑，讓報告反映同意與執行紀錄
            preview = run_autopilot(task, out_dir=out, consented=True)
            console.print("[green]已取得同意，安全動作已執行（需花錢的動作仍以計畫呈現，不會誤燒錢）。[/green]")
        else:
            console.print("[yellow]已停止自動執行。分析報告已完成，沒有任何花錢、寫入或發布動作被執行。[/yellow]")

    console.print()
    console.print("[bold green]完成！[/bold green]")
    console.print(f"給你的白話懶人包：{preview.beginner_path}")
    console.print(f"完整報告：{preview.report_path}")
    console.print(f"成本與影響明細：{preview.cost_estimate_path}")
    console.print(f"機器可讀資料：{preview.json_path}")


def demo(
    out: str = typer.Option("./auto-demo", "--out", help="輸出目錄"),
) -> None:
    """用內建範例目標跑一次一鍵顧問，全程免金鑰、不花錢。"""
    console.print("[cyan]這是示範模式，全程免金鑰、不會花任何錢。[/cyan]")
    task = AutoTask(target="https://example.com", industry="電商", mock=True)
    outcome = run_autopilot(task, out_dir=out, consented=False, on_progress=lambda m: console.print(f"[dim]{m}[/dim]"))
    console.print("[bold green]完成！[/bold green]")
    console.print(f"給你的白話懶人包：{outcome.beginner_path}")
    console.print(f"成本與影響明細：{outcome.cost_estimate_path}")
