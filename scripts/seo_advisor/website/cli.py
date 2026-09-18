"""Guided website commands. Build is offline; check always emits JSON."""

import json
from pathlib import Path
from typing import Annotated, Literal

import typer

from seo_advisor.website.builder import build_site, demo_brief, load_brief
from seo_advisor.website.check import check_site
from seo_advisor.website.models import WebsiteBrief

website_app = typer.Typer(help="引導建立 SEO／AEO 沉浸式網站（離線產出，不會自動部署或收款）")
DEFAULT_INIT_OUT = Path("./my-website")
DEFAULT_DEMO_OUT = Path("./website-demo")


def _build(brief: WebsiteBrief, out: Path, base: Path) -> None:
    try:
        result = build_site(brief, out, base_dir=base)
    except (ValueError, OSError) as exc:
        typer.echo(f"無法建立：{exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@website_app.command("init")
def init_site(out: Annotated[Path, typer.Option("--out")] = DEFAULT_INIT_OUT) -> None:
    """回答四個問題，產出可預覽、預設 noindex 的網站草稿。"""
    typer.echo("先做可預覽的草稿；圖像生成、內容確認及上線會在後續引導完成。")
    brand = typer.prompt("品牌或專案名稱", default="我的品牌")
    kind = typer.prompt("網站類型 sales（銷售）／shop（購物）／experience（體驗）", default="sales")
    hosting = typer.prompt("主機 cloudflare／firebase／gcp", default="cloudflare")
    canonical = typer.prompt(
        "正式網站根網址（尚未決定請直接 Enter）", default="", show_default=False
    )
    try:
        brief = WebsiteBrief(
            brand=brand, site_type=kind, hosting=hosting, canonical=canonical or None
        )
    except ValueError as exc:
        typer.echo(f"輸入有誤：{exc}", err=True)
        raise typer.Exit(1) from exc
    _build(brief, out, Path.cwd())


@website_app.command("build")
def build(
    brief: Annotated[Path, typer.Option("--brief", exists=True, dir_okay=False)],
    out: Annotated[Path, typer.Option("--out")],
) -> None:
    """依 JSON brief 產出靜態網站，只接受不存在的輸出目錄。"""
    try:
        parsed = load_brief(brief)
    except (ValueError, OSError) as exc:
        typer.echo(f"brief 有誤：{exc}", err=True)
        raise typer.Exit(1) from exc
    _build(parsed, out, brief.resolve().parent)


@website_app.command("demo")
def demo(
    out: Annotated[Path, typer.Option("--out")] = DEFAULT_DEMO_OUT,
    site_type: Annotated[Literal["sales", "shop", "experience"], typer.Option("--type")] = "sales",
    hosting: Annotated[
        Literal["cloudflare", "firebase", "gcp"], typer.Option("--hosting")
    ] = "cloudflare",
) -> None:
    """山嵐茶屋的虛構示範，無 API、無付費生圖、無自動部署。"""
    _build(demo_brief(site_type, hosting), out, Path.cwd())


@website_app.command("check")
def check(site: Annotated[Path, typer.Option("--site")]) -> None:
    """JSON 報告：exit 0=離線基線通過、2=草稿待補、1=驗證失敗。"""
    result = check_site(site)
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    raise typer.Exit({"baseline_ready": 0, "scaffold": 2, "invalid": 1}[result["status"]])
