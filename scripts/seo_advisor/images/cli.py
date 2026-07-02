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
