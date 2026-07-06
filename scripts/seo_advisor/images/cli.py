"""產圖素材專家的 CLI subapp（seo-advisor image ...）。"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from seo_advisor.errors import translate_exception
from seo_advisor.images.models import (
    AspectRatio,
    BrandKit,
    ImageGenerationRequest,
    ImageUseCase,
)
from seo_advisor.images.providers.factory import create_image_provider
from seo_advisor.images.runner import run_image_generation

image_app = typer.Typer(help="GPT 產圖素材專家：為廣告/社群/文章產生圖像素材")
console = Console()


def _run(provider_name: str, request: ImageGenerationRequest, out: str, *, debug: bool) -> None:
    try:
        provider = create_image_provider(provider_name)
        result = run_image_generation(
            provider, request, out_dir=out, on_progress=lambda m: console.print(f"[dim]{m}[/dim]")
        )
    except Exception as exc:  # noqa: BLE001 - 統一在 CLI 邊界轉成人話
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[bold green]完成！產出 {len(result.artifacts)} 張素材（provider：{result.provider}）。[/bold green]"
    )
    for artifact in result.artifacts:
        console.print(f"  {artifact.variant_label}：{artifact.path}（{artifact.width}x{artifact.height}）")
    console.print(f"素材清單：{Path(out) / 'image-manifest.json'}")
    if result.human_review_required:
        console.print("[yellow]提醒：廣告素材上架前建議由人工確認是否符合廣告政策與法規。[/yellow]")


@image_app.command("generate")
def generate(
    prompt: str = typer.Option(..., "--prompt", help="圖像描述"),
    use_case: str = typer.Option("social", "--use-case", help="用途：meta_ad/social/blog_hero/blog_inline/og_image/landing_page"),
    aspect: str = typer.Option("1:1", "--aspect", help="長寬比：1:1/4:5/9:16/16:9/3:2/2:3"),
    variants: int = typer.Option(1, "--variants", help="產生幾個變體"),
    brand: str = typer.Option(None, "--brand", help="品牌名稱（用於視覺一致性）"),
    negative_prompt: str = typer.Option(None, "--negative-prompt", help="不希望出現的元素"),
    provider: str = typer.Option("openai", "--provider", help="圖像 provider：openai/mock"),
    out: str = typer.Option("./image-assets", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """產生圖像素材。需要 OPENAI_API_KEY，或用 --provider mock 免金鑰試玩。"""
    try:
        parsed_use_case = ImageUseCase(use_case)
        parsed_aspect = AspectRatio(aspect)
    except ValueError as exc:
        console.print(f"[red]參數錯誤：{exc}[/red]")
        raise typer.Exit(code=1)

    request = ImageGenerationRequest(
        prompt=prompt,
        use_case=parsed_use_case,
        aspect_ratio=parsed_aspect,
        variants=variants,
        negative_prompt=negative_prompt,
        brand_kit=BrandKit(brand_name=brand) if brand else None,
    )
    _run(provider, request, out, debug=debug)


@image_app.command("demo")
def demo(
    out: str = typer.Option("./image-demo", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """用 mock provider 產生範例素材，不需要任何 API 金鑰。"""
    console.print("[cyan]這是示範模式，會用內建 mock provider 產生佔位素材，不會呼叫任何付費 API。[/cyan]")
    request = ImageGenerationRequest(
        prompt="（示範）SEO 健檢工具的社群宣傳圖",
        use_case=ImageUseCase.SOCIAL,
        aspect_ratio=AspectRatio.SQUARE,
        variants=3,
    )
    _run("mock", request, out, debug=debug)


@image_app.command("from-content")
def from_content(
    content_report: str = typer.Option(..., "--content-report", help="Content Writer 產出的 content-report.json 路徑"),
    provider: str = typer.Option("openai", "--provider", help="圖像 provider：openai/mock"),
    out: str = typer.Option("./content-images", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """讀取 Content Writer 報告，為該篇文章產生配圖（hero image）。"""
    try:
        data = json.loads(Path(content_report).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    topic = data.get("request", {}).get("topic", "文章配圖")
    request = ImageGenerationRequest(
        prompt=f"為「{topic}」這篇文章設計一張吸引人的封面配圖，風格清晰專業",
        use_case=ImageUseCase.BLOG_HERO,
        aspect_ratio=AspectRatio.LANDSCAPE_16_9,
        variants=2,
    )
    _run(provider, request, out, debug=debug)


@image_app.command("from-ads")
def from_ads(
    ads_report: str = typer.Option(..., "--ads-report", help="Meta 廣告診斷產出的 ads-report.json 路徑"),
    aspect: str = typer.Option("1:1", "--aspect", help="長寬比：1:1/4:5/9:16（廣告常用）"),
    variants: int = typer.Option(3, "--variants", help="產生幾個素材變體（預設 3：不同創意角度）"),
    brand: str = typer.Option(None, "--brand", help="品牌名稱（用於視覺一致性）"),
    angle: str = typer.Option(None, "--angle", help="指定創意角度覆寫（pain_point/benefit_outcome/social_proof）"),
    generate: bool = typer.Option(
        False, "--generate", help="真的呼叫 provider 產圖（會花費 API）；預設只產 brief，不花錢"
    ),
    confirm_low_confidence: bool = typer.Option(
        False,
        "--confirm-low-confidence",
        help="當主要素材機會信心較低時，仍要真產圖需明確加上此旗標",
    ),
    provider: str = typer.Option("openai", "--provider", help="圖像 provider：openai/mock"),
    out: str = typer.Option("./ad-creative", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """從廣告診斷報告，把素材疲勞等問題轉成新素材方向 brief。

    預設只產出 brief（image-brief.md/json，不花錢）；加 --generate 才真的產圖。
    """
    from seo_advisor.images.ads_bridge import (
        NoCreativeOpportunityError,
        build_image_request_from_ads,
        extract_creative_opportunities,
    )
    from seo_advisor.ads.models import AdsReport

    try:
        data = json.loads(Path(ads_report).read_text(encoding="utf-8"))
        report = AdsReport.model_validate(data)
        request, primary = build_image_request_from_ads(
            report, angle_override=angle, aspect_ratio=aspect, variants=variants, brand=brand
        )
        opportunities = extract_creative_opportunities(report)
    except NoCreativeOpportunityError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1)
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    # 一律先寫出 brief（給人看 + 機器可讀），不花錢。
    out_path = Path(out)
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "image-brief.md").write_text(
        _render_ads_brief(report, primary, opportunities, request), encoding="utf-8"
    )
    (out_path / "image-brief.json").write_text(
        json.dumps(
            {"request": request.model_dump(mode="json"),
             "opportunities": [o.model_dump(mode="json") for o in opportunities]},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    console.print(f"[green]已產生素材方向 brief：{out_path / 'image-brief.md'}[/green]")

    if not generate:
        console.print(
            "[cyan]目前只產出 brief，沒有花任何錢。確認方向後，加上 --generate 才會真的產圖"
            "（會用到 image provider API 費用；或用 --provider mock 免費試玩）。[/cyan]"
        )
        return

    # 低信心閘門：若主要機會信心較低（可能根本不是素材問題），真產圖需再明確確認，
    # 避免使用者白花錢產出無用素材。mock 免費，不受此閘門限制。
    if primary.needs_human_confirm and provider != "mock" and not confirm_low_confidence:
        console.print(
            "[yellow]這份報告的主要素材機會信心較低（可能不是素材問題，或缺乏 frequency/CTR 佐證）。"
            "為避免白花錢，已停在 brief。若你確認要產圖，請加上 --confirm-low-confidence，"
            "或先用 --provider mock 免費預覽。[/yellow]"
        )
        return

    if provider != "mock":
        console.print(
            f"[yellow]即將呼叫 {provider} 產生 {request.variants} 張素材，可能產生 API 費用。[/yellow]"
        )
    _run(provider, request, out, debug=debug)


def _render_ads_brief(report, primary, opportunities, request) -> str:
    lines = ["# 廣告素材方向 brief（由廣告診斷自動產生）", ""]
    lines.append(f"- 廣告帳戶健康分數：{report.account_health_score:.0f}/100")
    lines.append(f"- 主要素材機會：{primary.fatigue_reason}")
    if primary.needs_human_confirm:
        lines.append("- ⚠ 此機會信心較低，請先人工確認是否真的是素材問題。")
    lines.append("")
    lines.append("## 建議產出的素材 prompt")
    lines.append("")
    lines.append("```")
    lines.append(request.prompt)
    lines.append("```")
    lines.append("")
    lines.append("## 本次偵測到的所有素材機會（依優先順序）")
    lines.append("")
    for o in opportunities:
        flag = "（需人工確認）" if o.needs_human_confirm else ""
        lines.append(f"- [{o.severity}] {o.fatigue_reason} {flag}")
    lines.append("")
    lines.append("> 產出的是「該測哪些新創意角度」，不是換顏色的微調。上架前務必人工確認廣告政策與法規。")
    return "\n".join(lines)
