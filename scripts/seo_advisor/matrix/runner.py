"""矩陣執行協調：select_roles → build_assignments → run engines → synthesize
→ 輸出 Markdown + JSON 交付物。

CLI 的 matrix run / demo 都透過這裡執行，共用同一套流程與輸出格式。
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from seo_advisor.matrix.engines import create_engine
from seo_advisor.matrix.models import AgentRunResult, MatrixDeliverable, TaskRequest
from seo_advisor.matrix.planner import build_assignments
from seo_advisor.matrix.router import select_roles
from seo_advisor.matrix.synthesizer import synthesize

ProgressCallback = Callable[[str], None]


@dataclass
class MatrixOutcome:
    deliverable: MatrixDeliverable
    report_md_path: Path
    report_json_path: Path


def _noop(_: str) -> None:
    return None


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def run_matrix(
    task: TaskRequest,
    *,
    out_dir: str,
    provider_name: str = "mock",
    model: str | None = None,
    on_progress: ProgressCallback = _noop,
) -> MatrixOutcome:
    generated_at = _now_iso()

    on_progress("第 1/4 步：NORA 判斷任務、選擇 AI 工作夥伴")
    role_ids = select_roles(task)
    on_progress(f"已選擇 {len(role_ids)} 位夥伴：{', '.join(r.upper() for r in role_ids)}")

    on_progress("第 2/4 步：拆解任務、產生派工單（含安全升級）")
    assignments = build_assignments(task, role_ids)

    on_progress("第 3/4 步：各 AI 工作夥伴執行")
    results: list[AgentRunResult] = []
    for assignment in assignments:
        engine = create_engine(assignment.engine, provider_name=provider_name, model=model)
        results.append(engine.run(assignment, task))

    on_progress("第 4/4 步：NORA 整合成交付物並標記人工審核")
    deliverable = synthesize(task, assignments, results, generated_at=generated_at)

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    md_path = out_path / "matrix-report.md"
    json_path = out_path / "matrix-report.json"
    md_path.write_text(render_matrix_markdown(deliverable), encoding="utf-8")
    json_path.write_text(
        json.dumps(deliverable.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return MatrixOutcome(deliverable=deliverable, report_md_path=md_path, report_json_path=json_path)


def render_matrix_markdown(d: MatrixDeliverable) -> str:
    lines: list[str] = []
    lines.append(f"# AI 矩陣營運系統交付報告：{d.user_goal}")
    lines.append("")
    lines.append(f"- 產生時間：{d.generated_at}")
    lines.append(f"- 啟用夥伴：{'、'.join(r.upper() for r in d.selected_roles)}")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append("")
    lines.append(d.executive_summary)
    lines.append("")

    if d.human_review_required:
        lines.append("> ⚠ 本交付包含需要人工確認的項目（預算／法務／財務／對外發布等），"
                     "請先審核再執行。")
        lines.append("")

    lines.append("## 各 AI 工作夥伴的產出")
    lines.append("")
    for result in d.role_results:
        role_upper = result.role_id.upper()
        flag = "（需人工確認）" if result.status == "needs_review" else ""
        lines.append(f"### {role_upper}{flag}")
        lines.append("")
        lines.append(result.summary)
        lines.append("")
        for item in result.action_items:
            hr = "（需人工確認）" if item.human_review_required else ""
            lines.append(f"- **{item.title}**{hr}：{item.detail}")
        lines.append("")

    lines.append("## 整合行動清單")
    lines.append("")
    for item in d.integrated_plan:
        hr = "（需人工確認）" if item.human_review_required else ""
        lines.append(f"- [{item.role_id.upper()}] **{item.title}**{hr}：{item.detail}")
    lines.append("")

    if d.risks:
        lines.append("## 需要人工確認的風險項目")
        lines.append("")
        for risk in d.risks:
            lines.append(f"- [{risk.role_id.upper()}][{risk.severity}] {risk.reason}")
        lines.append("")

    lines.append("## 下一步")
    lines.append("")
    for step in d.next_steps:
        lines.append(f"- {step}")
    lines.append("")

    return "\n".join(lines)
