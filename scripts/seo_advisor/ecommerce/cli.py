"""電商 listing 健檢的 CLI subapp（seo-advisor ecommerce ...）。"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from seo_advisor.ecommerce.analyzer import analyze_listing
from seo_advisor.ecommerce.models import EcommerceListing
from seo_advisor.ecommerce.report import render_ecommerce_json, render_ecommerce_markdown
from seo_advisor.errors import translate_exception

ecommerce_app = typer.Typer(help="Amazon / 電商平台 listing 健檢（中性化蒸餾方法論，免金鑰）")
console = Console()

_DEMO_LISTING = EcommerceListing(
    title="無線藍牙耳機",
    bullet_points=["降噪", "電量持久"],
    backend_keywords=["耳機"],
    main_image_present=True,
    secondary_image_count=1,
    has_a_plus_content=False,
    review_count=4,
    rating=3.6,
    in_stock=True,
    has_buy_box=True,
    variations_count=2,
)


def _run(listing: EcommerceListing, out: str, *, debug: bool) -> None:
    try:
        report = analyze_listing(listing)
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    out_path = Path(out)
    out_path.mkdir(parents=True, exist_ok=True)
    md_path = out_path / "ecommerce-report.md"
    json_path = out_path / "ecommerce-report.json"
    md_path.write_text(render_ecommerce_markdown(report), encoding="utf-8")
    json_path.write_text(render_ecommerce_json(report), encoding="utf-8")

    console.print(f"[bold green]完成！Listing 健康分數：{report.listing_health_score:.0f}/100，"
                  f"共 {len(report.findings)} 項發現。[/bold green]")
    console.print(f"報告：{md_path}")
    console.print(f"機器可讀資料：{json_path}")


@ecommerce_app.command("audit")
def audit(
    input: str = typer.Option(..., "--input", help="listing 資訊的 JSON 檔路徑"),
    out: str = typer.Option("./ecommerce-report", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """依 JSON 提供的 listing 資訊做健檢。JSON 欄位見 EcommerceListing 模型。"""
    try:
        data = json.loads(Path(input).read_text(encoding="utf-8"))
        listing = EcommerceListing.model_validate(data)
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)
    _run(listing, out, debug=debug)


@ecommerce_app.command("demo")
def demo(
    out: str = typer.Option("./ecommerce-demo", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """用內建範例 listing 跑一次健檢，不需要任何 API 金鑰。"""
    console.print("[cyan]這是示範模式，使用內建範例 listing 資料。[/cyan]")
    _run(_DEMO_LISTING, out, debug=debug)
