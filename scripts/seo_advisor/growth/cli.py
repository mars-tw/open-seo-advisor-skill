"""成長行銷模組的 CLI subapp（seo-advisor growth ...）。"""

from __future__ import annotations

import typer
from rich.console import Console

from seo_advisor.errors import translate_exception
from seo_advisor.growth.runner import run_analytics, run_cro, run_utm

growth_app = typer.Typer(help="成長行銷：UTM 歸因、CRO 落地頁優化、跨渠道成效分析")
console = Console()


@growth_app.command("utm")
def utm(
    url: str = typer.Option(..., "--url", help="要加上 UTM 的目標網址"),
    channels: str = typer.Option(
        "google,facebook,instagram,email", "--channels", help="逗號分隔的渠道，例如 google,facebook,email"
    ),
    out: str = typer.Option("./growth-utm", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """產生一致命名的 UTM tagged URL、命名規範與歸因衛生檢查。"""
    try:
        channel_list = [c.strip() for c in channels.split(",") if c.strip()]
        plan, md_path, json_path = run_utm(url, channel_list, out)
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold green]完成！已為 {len(plan.channels)} 個渠道產生 UTM，"
                  f"歸因檢查發現 {len(plan.audit_items)} 項提醒。[/bold green]")
    console.print(f"UTM 計畫：{md_path}")
    console.print(f"機器可讀資料：{json_path}")


@growth_app.command("cro")
def cro(
    url: str = typer.Option(..., "--url", help="要診斷的落地頁網址"),
    no_fetch: bool = typer.Option(False, "--no-fetch", help="不抓取頁面，只給通用 CRO 規劃"),
    out: str = typer.Option("./growth-cro", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """診斷落地頁的轉換率優化機會並設計 A/B 測試。"""
    try:
        report, md_path, json_path = run_cro(url, out, fetch=not no_fetch)
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold green]完成！CRO 診斷 {len(report.findings)} 項發現，"
                  f"{len(report.ab_test_ideas)} 個 A/B 測試點子。[/bold green]")
    console.print(f"CRO 報告：{md_path}")
    console.print(f"機器可讀資料：{json_path}")


@growth_app.command("analytics")
def analytics(
    provider: str = typer.Option("mock", "--provider", help="資料來源：mock/ga4/search_console/google_ads"),
    property_id: str = typer.Option("demo", "--property", help="GA4 property / GSC site / Ads account 識別"),
    since: int = typer.Option(30, "--since-days", help="觀察天數"),
    out: str = typer.Option("./growth-analytics", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """跨渠道成效分析（read-only）。無金鑰時用 --provider mock 完整試玩。"""
    try:
        report, md_path, json_path = run_analytics(provider, property_id, since, out)
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold green]完成！分析 {len(report.rows)} 個渠道，"
                  f"發現 {len(report.findings)} 項成效問題。[/bold green]")
    console.print(f"成效分析報告：{md_path}")
    console.print(f"機器可讀資料：{json_path}")


@growth_app.command("demo")
def demo(
    out: str = typer.Option("./growth-demo", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """一次示範 UTM + CRO + 成效分析，全部免金鑰。"""
    console.print("[cyan]這是示範模式，UTM/CRO 用純邏輯、成效分析用 mock 資料，全部免金鑰。[/cyan]")
    try:
        run_utm("https://example.com/promo", ["google", "facebook", "email", "line"], out)
        run_cro("https://example.com/lp", out, fetch=False)
        run_analytics("mock", "demo", 30, out)
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[bold green]完成！三份範例報告已輸出到 {out}[/bold green]")
