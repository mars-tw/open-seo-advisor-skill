"""AI 矩陣營運系統的 CLI subapp（seo-advisor matrix ...）。"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from seo_advisor.errors import translate_exception
from seo_advisor.matrix.models import TaskRequest
from seo_advisor.matrix.registry import all_roles, get_role
from seo_advisor.matrix.runner import run_matrix

matrix_app = typer.Typer(help="AI 矩陣營運系統：一句目標，NORA 自動派工給多位 AI 工作夥伴協作")
console = Console()


def _run(task: TaskRequest, out: str, provider: str, model: str | None, *, debug: bool) -> None:
    try:
        outcome = run_matrix(
            task,
            out_dir=out,
            provider_name=provider,
            model=model,
            on_progress=lambda m: console.print(f"[dim]{m}[/dim]"),
        )
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    d = outcome.deliverable
    console.print(
        f"[bold green]完成！NORA 啟用了 {len(d.selected_roles)} 位夥伴，"
        f"整合出 {len(d.integrated_plan)} 項行動。[/bold green]"
    )
    console.print(f"交付報告：{outcome.report_md_path}")
    console.print(f"機器可讀資料：{outcome.report_json_path}")
    if d.human_review_required:
        console.print("[yellow]提醒：本交付包含需人工確認的項目（預算/法務/財務/對外發布），"
                      "請先審核再執行。[/yellow]")


@matrix_app.command("run")
def run(
    goal: str = typer.Option(None, "--goal", help="你的目標，例如「規劃下個月的成長方案」"),
    industry: str = typer.Option(None, "--industry", help="行業，例如 製造業 / 餐飲 / B2B SaaS"),
    input: str = typer.Option(None, "--input", help="改用 JSON 檔輸入任務（與 --goal 擇一）"),
    provider: str = typer.Option("mock", "--provider", help="LLM provider：mock/anthropic/openai/local"),
    model: str = typer.Option(None, "--model", help="覆寫模型名稱"),
    out: str = typer.Option("./matrix-report", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """依你的目標，由 NORA 自動組合 AI 工作夥伴協作產出可執行方案。"""
    if input:
        try:
            data = json.loads(Path(input).read_text(encoding="utf-8"))
            task = TaskRequest.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            if debug:
                raise
            console.print(f"[red]{translate_exception(exc).render()}[/red]")
            raise typer.Exit(code=1)
    elif goal:
        task = TaskRequest(user_goal=goal, industry=industry)
    else:
        console.print("[red]錯誤：請提供 --goal 或 --input 其中之一。[/red]")
        console.print("[dim]想先看範例嗎？執行 seo-advisor matrix demo[/dim]")
        raise typer.Exit(code=1)

    _run(task, out, provider, model, debug=debug)


@matrix_app.command("demo")
def demo(
    out: str = typer.Option("./matrix-demo", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """用內建範例任務（製造業新品上市）跑一次完整矩陣協作，不需要任何 API 金鑰。"""
    console.print("[cyan]這是示範模式，會用 mock 引擎跑完整矩陣協作，不需要任何 API 金鑰。[/cyan]")
    task = TaskRequest(
        task_id="demo",
        user_goal="推廣一款新的工業零件，增加海外 B2B 詢價",
        industry="製造業",
    )
    _run(task, out, provider="mock", model=None, debug=debug)


@matrix_app.command("roles")
def roles() -> None:
    """列出所有 AI 工作夥伴角色。"""
    for role in all_roles():
        review = "（需人工審核）" if role.human_review_required else ""
        console.print(f"[bold]{role.display_name}[/bold]（{role.id}）- {role.title}{review}")


@matrix_app.command("role")
def role_detail(role_id: str) -> None:
    """查看單一角色的詳細資訊。"""
    role = get_role(role_id)
    if role is None:
        console.print(f"[red]找不到角色：{role_id}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[bold]{role.display_name}[/bold]（{role.id}）- {role.title}")
    console.print(f"職責：{role.mission}")
    console.print(f"能力：{', '.join(role.capabilities)}")
    console.print(f"引擎：{role.default_engine.value}")
    console.print(f"安全等級：{role.safety_level.value}｜寫入政策：{role.write_policy.value}"
                  f"｜需人工審核：{'是' if role.human_review_required else '否'}")
    if role.safety_notes:
        console.print("安全注意事項：")
        for note in role.safety_notes:
            console.print(f"  - {note}")
