"""Meta 廣告優化專家的 CLI subapp（seo-advisor ads ...）。

安全設計：
- audit / plan / demo 都是唯讀或 dry-run，不會動用真實預算。
- apply（實際代操）刻意「尚未開放」：動用真實廣告預算是最高風險操作，
  目前的整體流程為 audit → plan（dry-run）→ 人工檢視 action-plan.json →
  手動到 Meta 後台套用。自動化 apply 會在 AdsSafetyPolicy 防護經充分驗證後
  於後續版本才逐步開放。
"""

from __future__ import annotations

import typer
from rich.console import Console

from seo_advisor.ads.models import AdsSafetyPolicy
from seo_advisor.ads.providers.factory import create_ads_provider
from seo_advisor.ads.runner import run_ads_audit, run_ads_plan
from seo_advisor.errors import translate_exception

ads_app = typer.Typer(help="Meta 廣告優化專家：診斷廣告帳戶並產出優化建議與行動計畫")
console = Console()


def _parse_since(since: str) -> int:
    s = since.strip().lower().rstrip("d")
    try:
        return max(1, int(s))
    except ValueError:
        return 30


@ads_app.command("audit")
def audit(
    account: str = typer.Option(..., "--account", help="廣告帳戶 ID（例如 act_123456）"),
    since: str = typer.Option("30d", "--since", help="觀察期間，例如 7d / 30d"),
    provider: str = typer.Option("meta", "--provider", help="廣告 provider：meta/mock"),
    out: str = typer.Option("./ads-report", "--out", help="報告輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """唯讀健檢：診斷廣告帳戶並產出優化建議報告（不會修改任何東西）。"""
    policy = AdsSafetyPolicy(allowed_capabilities={"ads_read"})
    try:
        ads_provider = create_ads_provider(provider)
        outcome = run_ads_audit(
            ads_provider,
            account_id=account,
            since_days=_parse_since(since),
            out_dir=out,
            policy=policy,
            on_progress=lambda m: console.print(f"[dim]{m}[/dim]"),
        )
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[bold green]完成！帳戶健康分數：{outcome.report.account_health_score:.0f}/100，"
        f"共 {len(outcome.report.findings)} 項發現。[/bold green]"
    )
    console.print(f"報告：{outcome.report_md_path}")
    console.print(f"機器可讀資料：{outcome.report_json_path}")


@ads_app.command("plan")
def plan(
    account: str = typer.Option(..., "--account", help="廣告帳戶 ID"),
    since: str = typer.Option("30d", "--since", help="觀察期間，例如 7d / 30d"),
    provider: str = typer.Option("meta", "--provider", help="廣告 provider：meta/mock"),
    out: str = typer.Option("./ads-plan", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """產出 dry-run 行動計畫（action-plan.json），不會實際修改廣告帳戶。"""
    policy = AdsSafetyPolicy(allowed_capabilities={"ads_read"})
    try:
        ads_provider = create_ads_provider(provider)
        outcome = run_ads_plan(
            ads_provider,
            account_id=account,
            since_days=_parse_since(since),
            out_dir=out,
            policy=policy,
            on_progress=lambda m: console.print(f"[dim]{m}[/dim]"),
        )
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[bold green]完成！產出 {len(outcome.plan.actions)} 個建議動作（dry-run）。[/bold green]"
    )
    console.print(f"行動計畫：{outcome.plan_json_path}")
    console.print("[yellow]提醒：這是 dry-run 計畫，不會自動執行。請人工檢視後，"
                  "手動到 Meta 廣告管理員套用。[/yellow]")


@ads_app.command("demo")
def demo(
    out: str = typer.Option("./ads-demo", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """用 mock provider 產生範例廣告健檢報告，不需要 Meta API 金鑰。"""
    console.print("[cyan]這是示範模式，會用內建 mock 廣告帳戶資料，不會連接任何真實廣告帳戶。[/cyan]")
    policy = AdsSafetyPolicy(allowed_capabilities={"ads_read"})
    try:
        ads_provider = create_ads_provider("mock")
        outcome = run_ads_plan(
            ads_provider,
            account_id="act_demo",
            since_days=30,
            out_dir=out,
            policy=policy,
            on_progress=lambda m: console.print(f"[dim]{m}[/dim]"),
        )
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[bold green]完成！帳戶健康分數：{outcome.report.account_health_score:.0f}/100，"
        f"產出 {len(outcome.plan.actions)} 個建議動作。[/bold green]"
    )
    console.print(f"報告：{outcome.report_md_path}")
    console.print(f"行動計畫：{outcome.plan_json_path}")


@ads_app.command("apply")
def apply(
    plan: str = typer.Option(..., "--plan", help="要套用的 action-plan.json 路徑"),
) -> None:
    """（尚未開放）實際套用行動計畫到 Meta 廣告帳戶。"""
    console.print(
        "[yellow]實際代操（動用真實廣告預算）尚未在此版本開放。[/yellow]\n"
        "目前的安全流程為：audit → plan（dry-run）→ 人工檢視 action-plan.json → "
        "手動到 Meta 廣告管理員套用。\n"
        "自動化 apply 會在 AdsSafetyPolicy 防護與回滾機制經充分驗證後，"
        "於後續版本才逐步開放，且會擴大花費的動作（增加預算、啟用投放）預設仍鎖住。"
    )
    raise typer.Exit(code=1)
