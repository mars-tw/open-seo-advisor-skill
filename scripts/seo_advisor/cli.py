"""Open SEO Advisor CLI 入口。

新手用法（不需要記任何參數）：
    seo-advisor
    seo-advisor start

進階用法：
    seo-advisor audit consultant --url example.com --out ./report
    seo-advisor audit consultant --source ./my-site --out ./report
    seo-advisor demo

任何指令加上 --debug 都會在發生錯誤時顯示完整技術細節（Python traceback），
預設情況下只會顯示人話說明與建議的下一步，避免嚇到不熟悉程式的使用者。
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from seo_advisor.demo import run_demo_scan
from seo_advisor.errors import translate_exception
from seo_advisor.models import Mode
from seo_advisor.router import ModeNotImplementedError, UnknownModeError, ensure_implemented, resolve_mode
from seo_advisor.scan_runner import ScanOutcome, run_consultant_scan
from seo_advisor.wizard import run_wizard
from seo_advisor.writers.models import ContentRequest, SearchIntent
from seo_advisor.writers.pipeline import run_content_writer_pipeline
from seo_advisor.writers.providers.factory import create_provider
from seo_advisor.writers.render import (
    render_content_report_json,
    render_content_report_markdown,
    render_final_draft_markdown,
)

app = typer.Typer(
    help=(
        "Open SEO Advisor - 開源全域行銷營運技能。\n\n"
        "新手只要記這一個：\n"
        "  seo-advisor auto <你的網址>   （一個指令搞定，預設不花錢）\n\n"
        "不想記指令？直接輸入 seo-advisor 進問答精靈，一步步引導你。\n"
        "想先看範例？seo-advisor auto-demo（免金鑰）。\n\n"
        "（進階使用者：還有 audit/write/ads/image/growth/ecommerce/matrix 等"
        "指令，完整清單見 docs/capability-map.md。）"
    ),
    invoke_without_command=True,
)
audit_app = typer.Typer(help="執行 SEO 健檢（顧問模式等，進階用法）")
app.add_typer(audit_app, name="audit")

from seo_advisor.ads.cli import ads_app  # noqa: E402 - 延後匯入避免循環相依
from seo_advisor.autopilot.cli import auto as _auto_command  # noqa: E402
from seo_advisor.autopilot.cli import demo as _auto_demo_command  # noqa: E402
from seo_advisor.ecommerce.cli import ecommerce_app  # noqa: E402 - 延後匯入避免循環相依
from seo_advisor.growth.cli import growth_app  # noqa: E402 - 延後匯入避免循環相依
from seo_advisor.images.cli import image_app  # noqa: E402 - 延後匯入避免循環相依
from seo_advisor.matrix.cli import matrix_app  # noqa: E402 - 延後匯入避免循環相依

app.add_typer(image_app, name="image")
app.add_typer(ads_app, name="ads")
app.add_typer(matrix_app, name="matrix")
app.add_typer(growth_app, name="growth")
app.add_typer(ecommerce_app, name="ecommerce")

# 一鍵代操機器人：頂層指令，新手最推薦的入口
app.command("auto")(_auto_command)
app.command("auto-demo")(_auto_demo_command)

console = Console()


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        run_wizard(console)


@app.command("start")
def start(
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """新手推薦入口：用問答方式引導完成第一次 SEO 健檢。"""
    run_wizard(console, debug=debug)


@app.command("demo")
def demo(
    out: str = typer.Option("./seo-demo-report", "--out", help="報告輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """不需要輸入任何網址，直接看一份範例 SEO 健檢報告長什麼樣子。"""
    console.print("[cyan]這是示範模式，會使用內建的範例網站資料，不會真的連到網路上的任何網站。[/cyan]")
    _run_scan(lambda progress: run_demo_scan(out_dir=out, on_progress=progress), debug=debug)


@audit_app.command("consultant")
def audit_consultant(
    url: str = typer.Option(None, "--url", help="要檢查的網站 URL（與 --source 擇一，可省略 https://）"),
    source: str = typer.Option(None, "--source", help="本地原始碼包或目錄路徑（與 --url 擇一）"),
    out: str = typer.Option("./report", "--out", help="報告輸出目錄"),
    max_urls: int = typer.Option(200, "--max-urls", help="最多爬取的 URL 數量"),
    max_depth: int = typer.Option(6, "--max-depth", help="最大爬取深度"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """執行顧問模式（Consultant Mode）全站 SEO 健檢（進階指令，新手建議改用 `seo-advisor start`）。"""

    ensure_implemented(Mode.CONSULTANT)

    if not url and not source:
        console.print("[red]錯誤：必須提供 --url 或 --source 其中之一。[/red]")
        console.print("[dim]不確定怎麼用嗎？直接執行 `seo-advisor start` 會用問答方式引導你。[/dim]")
        raise typer.Exit(code=1)
    if url and source:
        console.print("[red]錯誤：--url 與 --source 不可同時提供，請擇一使用。[/red]")
        raise typer.Exit(code=1)

    _run_scan(
        lambda progress: run_consultant_scan(
            url=url, source=source, out_dir=out, max_urls=max_urls, max_depth=max_depth, on_progress=progress
        ),
        debug=debug,
    )


@app.command("write")
def write_content(
    topic: str = typer.Option(None, "--topic", help="文章主題（用 --from-report 時可省略，會自動萃取）"),
    from_report: str = typer.Option(
        None, "--from-report", help="顧問報告 JSON 路徑，自動把 SEO 缺口轉成寫作 brief"
    ),
    lang: str = typer.Option("zh-TW", "--lang", help="撰寫語言，例如 zh-TW、en-US"),
    locale: str = typer.Option(None, "--locale", help="地區代碼，例如 TW、US"),
    audience: str = typer.Option(None, "--audience", help="目標讀者描述"),
    intent: str = typer.Option(
        None,
        "--intent",
        help="搜尋意圖：informational/commercial/transactional/navigational/local/mixed",
    ),
    industry: str = typer.Option(None, "--industry", help="產業別"),
    brand_context: str = typer.Option(None, "--brand-context", help="品牌或產品背景說明"),
    llm_provider: str = typer.Option(
        "anthropic", "--llm-provider", help="LLM 供應商：anthropic/openai/local/mock"
    ),
    model: str = typer.Option(None, "--model", help="覆寫預設模型名稱"),
    auto_revise: bool = typer.Option(False, "--auto-revise", help="QA 未通過時自動修訂草稿"),
    out: str = typer.Option("./content-report", "--out", help="報告輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """執行文章寫手模式（Content Writer Mode），產出符合 SEO 品質規範的文章草稿。

    需要對應 provider 的 API 金鑰（例如 ANTHROPIC_API_KEY），或使用
    --llm-provider local 呼叫本機 Ollama 服務（不需要 API 金鑰）。
    """
    if not topic and not from_report:
        console.print("[red]錯誤：請提供 --topic 指定主題，或用 --from-report 從顧問報告自動產生。[/red]")
        raise typer.Exit(code=1)

    try:
        parsed_intent = SearchIntent(intent) if intent else None
    except ValueError:
        valid = ", ".join(i.value for i in SearchIntent)
        console.print(f"[red]錯誤：--intent 只接受以下選項：{valid}[/red]")
        raise typer.Exit(code=1)

    if from_report:
        # 從顧問報告萃取內容 brief。使用者的 --topic 永遠優先當 override。
        from seo_advisor.models import Report
        from seo_advisor.writers.report_bridge import (
            NoContentOpportunityError,
            build_content_request_from_report,
        )

        try:
            report_data = json.loads(Path(from_report).read_text(encoding="utf-8"))
            report = Report.model_validate(report_data)
            request = build_content_request_from_report(
                report,
                topic_override=topic,
                audience=audience,
                lang=lang,
                locale=locale,
                industry=industry,
                brand_context=brand_context,
                auto_revise=auto_revise,
            )
        except NoContentOpportunityError as exc:
            console.print(f"[yellow]{exc}[/yellow]")
            raise typer.Exit(code=1)
        except Exception as exc:  # noqa: BLE001
            if debug:
                raise
            console.print(f"[red]{translate_exception(exc).render()}[/red]")
            raise typer.Exit(code=1)
        if parsed_intent:
            request.intent = parsed_intent
        console.print(f"[cyan]已從報告萃取寫作 brief，主題：{request.topic}[/cyan]")
    else:
        request = ContentRequest(
            topic=topic,
            lang=lang,
            locale=locale,
            audience=audience,
            intent=parsed_intent,
            industry=industry,
            brand_context=brand_context,
            auto_revise=auto_revise,
        )

    try:
        provider = create_provider(llm_provider, model=model)
        result = run_content_writer_pipeline(
            provider, request, on_progress=lambda msg: console.print(f"[dim]{msg}[/dim]")
        )
    except Exception as exc:  # noqa: BLE001 - 統一在 CLI 邊界把例外轉成人話說明
        if debug:
            raise
        friendly = translate_exception(exc)
        console.print(f"[red]{friendly.render()}[/red]")
        raise typer.Exit(code=1)

    out_path = Path(out)
    out_path.mkdir(parents=True, exist_ok=True)
    report_path = out_path / "content-report.md"
    json_path = out_path / "content-report.json"
    draft_path = out_path / "draft.md"

    report_path.write_text(render_content_report_markdown(result), encoding="utf-8")
    json_path.write_text(render_content_report_json(result), encoding="utf-8")
    draft_path.write_text(render_final_draft_markdown(result), encoding="utf-8")

    status = "通過" if result.qa.passed else "需要人工修正"
    console.print(
        f"[bold green]完成！品質審核：{status}（分數 {result.qa.quality_score:.0f}/100）[/bold green]"
    )
    console.print(f"可直接使用的草稿：{draft_path}")
    console.print(f"完整報告（含 brief/outline/QA）：{report_path}")
    console.print(f"機器可讀資料：{json_path}")
    if result.brief.is_ymyl:
        console.print("[yellow]提醒：這是 YMYL 主題，發布前建議由領域專家審核。[/yellow]")


@app.command("mode")
def show_mode_status(name: str) -> None:
    """查詢指定模式的實作狀態（給想知道 Engineer/Security 等模式進度的使用者）。"""
    try:
        mode = resolve_mode(name)
    except UnknownModeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)

    try:
        ensure_implemented(mode)
        console.print(f"[green]模式 {mode.value} 已實作，可直接使用。[/green]")
    except ModeNotImplementedError as exc:
        console.print(f"[yellow]{exc}[/yellow]")


def _run_scan(scan_fn, *, debug: bool) -> None:
    try:
        outcome: ScanOutcome = scan_fn(lambda msg: console.print(f"[dim]{msg}[/dim]"))
    except Exception as exc:  # noqa: BLE001 - 統一在 CLI 邊界把例外轉成人話說明
        if debug:
            raise
        friendly = translate_exception(exc)
        console.print(f"[red]{friendly.render()}[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[bold green]完成！健康分數：{outcome.report.site_health_score:.0f}/100，"
        f"共 {len(outcome.report.findings)} 項發現。[/bold green]"
    )
    console.print(f"給非技術人員看的懶人包：{outcome.beginner_path}")
    console.print(f"完整技術報告：{outcome.technical_path}")
    console.print(f"機器可讀資料：{outcome.json_path}")


if __name__ == "__main__":
    app()
