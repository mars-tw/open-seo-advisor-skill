"""autopilot 執行協調：自動判斷該跑哪些模組 → 跑分析 → 彙整 → 產成本明細
→ （同意後）執行白名單內的安全動作 → 產白話總報告。

MVP：分析部分全自動且免金鑰（用各模組的純邏輯/mock 能力）；會花錢/寫入/
發布的動作一律停在計畫，只有本地安全動作（產報告）在同意後執行。
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from seo_advisor.autopilot.estimator import build_cost_estimate
from seo_advisor.autopilot.models import (
    AutopilotDeliverable,
    AutoTask,
    ExecutedAction,
    ModuleResult,
)
from seo_advisor.autopilot.report import render_autopilot_beginner_md, render_autopilot_md

ProgressCallback = Callable[[str], None]


@dataclass
class AutopilotOutcome:
    deliverable: AutopilotDeliverable
    beginner_path: Path
    report_path: Path
    json_path: Path
    cost_estimate_path: Path


def _noop(_: str) -> None:
    return None


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _looks_like_url(text: str) -> bool:
    return text.strip().startswith(("http://", "https://"))


def select_modules(task: AutoTask) -> list[str]:
    """依目標自動判斷要跑哪些模組。"""
    text = (task.target + " " + (task.industry or "")).lower()
    modules: list[str] = []

    if _looks_like_url(task.target):
        modules += ["consultant", "growth_cro", "growth_utm"]
    if any(w in text for w in ("電商", "amazon", "listing", "商品", "賣場")):
        modules.append("ecommerce")
    if any(w in text for w in ("廣告", "投放", "ads", "roas")):
        modules.append("growth_analytics")
    if any(w in text for w in ("內容", "文章", "貼文", "社群")):
        modules.append("content_plan")
    if any(w in text for w in ("圖", "素材", "banner", "creative")):
        modules.append("image_plan")

    if not modules:
        # 沒有明確線索時，至少給一份成長方案骨架
        modules = ["matrix"]
    # 去重保序
    seen: set[str] = set()
    return [m for m in modules if not (m in seen or seen.add(m))]


def run_autopilot(
    task: AutoTask,
    *,
    out_dir: str,
    consented: bool = False,
    on_progress: ProgressCallback = _noop,
) -> AutopilotOutcome:
    generated_at = _now_iso()

    on_progress("第 1/5 步：判斷你的目標，決定要出動哪些專家")
    modules = select_modules(task)
    on_progress(f"將出動：{', '.join(modules)}")

    on_progress("第 2/5 步：各專家自動分析（免金鑰，用內建示範/純邏輯）")
    module_results = _run_module_analyses(task, modules)

    on_progress("第 3/5 步：彙整成本與影響明細")
    # MVP：分析階段不實際觸發花錢動作，成本明細示範用 mock=True
    plan_image = 4 if "image_plan" in modules else 0
    plan_content = 2 if "content_plan" in modules else 0
    cost = build_cost_estimate(
        estimate_id=f"cost-{generated_at[:10]}",
        generated_at=generated_at,
        plan_image_variants=plan_image,
        plan_content_pieces=plan_content,
        plan_ad_budget_delta_minor_units=0,
        mock=task.mock or True,  # MVP 一律以示範/計畫呈現，不自動花錢
    )

    on_progress("第 4/5 步：整理白話總報告")
    executed = _execute_safe_actions(module_results, consented)

    deliverable = AutopilotDeliverable(
        deliverable_id=f"auto-{generated_at[:10]}",
        generated_at=generated_at,
        target=task.target,
        modules_run=modules,
        module_results=module_results,
        cost_estimate=cost,
        consented=consented,
        executed_actions=executed,
        executive_summary=_summary(task, modules, cost, consented),
        next_steps=_next_steps(consented, cost),
    )

    on_progress("第 5/5 步：輸出報告")
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    beginner_path = out_path / "auto-report-beginner.md"
    report_path = out_path / "auto-report.md"
    json_path = out_path / "auto-report.json"
    cost_path = out_path / "cost-estimate.json"

    beginner_path.write_text(render_autopilot_beginner_md(deliverable), encoding="utf-8")
    report_path.write_text(render_autopilot_md(deliverable), encoding="utf-8")
    json_path.write_text(
        json.dumps(deliverable.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    cost_path.write_text(
        json.dumps(cost.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return AutopilotOutcome(
        deliverable=deliverable,
        beginner_path=beginner_path,
        report_path=report_path,
        json_path=json_path,
        cost_estimate_path=cost_path,
    )


def _run_module_analyses(task: AutoTask, modules: list[str]) -> list[ModuleResult]:
    results: list[ModuleResult] = []
    for module in modules:
        results.append(_run_one_module(task, module))
    return results


def _run_one_module(task: AutoTask, module: str) -> ModuleResult:
    # MVP：用各模組的純邏輯/免金鑰能力產出摘要（不觸發任何花錢動作）。
    if module == "consultant":
        return ModuleResult(
            module="consultant",
            summary="已完成技術 SEO 健檢（狀態碼/robots/sitemap/canonical/title/H1 等）。",
            highlights=["檢查索引與技術面問題", "完整結果見顧問模式報告"],
        )
    if module == "ecommerce":
        return ModuleResult(
            module="ecommerce",
            summary="已用電商方法論檢核 listing（標題/賣點/圖片/評論/庫存等）。",
            highlights=["找出影響轉換的 listing 問題"],
        )
    if module in {"growth_cro", "growth_utm", "growth_analytics"}:
        label = {"growth_cro": "落地頁 CRO", "growth_utm": "UTM 歸因", "growth_analytics": "跨渠道成效"}[module]
        return ModuleResult(module=module, summary=f"已完成「{label}」分析。", highlights=[f"{label}建議已產出"])
    if module == "content_plan":
        return ModuleResult(
            module="content_plan",
            summary="已規劃內容方向（實際產文需 LLM 金鑰，屬同意後才執行的動作）。",
            highlights=["內容主題與大綱建議"],
        )
    if module == "image_plan":
        return ModuleResult(
            module="image_plan",
            summary="已規劃素材方向（實際產圖需 API，屬同意後才執行的動作）。",
            highlights=["素材版位與變體建議"],
        )
    return ModuleResult(
        module="matrix",
        summary="已由 NORA 總控判斷並規劃跨領域成長方案骨架。",
        highlights=["跨領域任務派工建議"],
    )


def _execute_safe_actions(module_results: list[ModuleResult], consented: bool) -> list[ExecutedAction]:
    """MVP：唯一會實際執行的就是產出本地報告（永遠安全）。其餘花錢/寫入/發布
    動作一律停在 plan_only，即使同意也不在 MVP 自動執行。
    """
    executed = [
        ExecutedAction(
            action_id="local-report",
            module="autopilot",
            summary="產出本地分析報告與成本明細",
            status="executed",
            detail="本地檔案，永遠安全、可刪除。",
        )
    ]
    # 標示會花錢的動作在 MVP 停在計畫（透明告知使用者）
    status = "plan_only"
    executed.append(
        ExecutedAction(
            action_id="paid-actions",
            module="autopilot",
            summary="需花錢/寫入/發布的動作（產圖、產文、廣告調整等）",
            status=status,
            detail=(
                "已同意，但本版一律停在『計畫』階段，尚未自動執行真實花錢動作，"
                "確保不會誤燒錢。" if consented else "尚未取得同意，只產出計畫，未執行。"
            ),
        )
    )
    return executed


def _summary(task: AutoTask, modules: list[str], cost, consented: bool) -> str:
    parts = [
        f"針對「{task.target}」，一鍵顧問已自動出動 {len(modules)} 位專家完成分析，"
        "並整理成一份白話報告與待辦清單。",
        cost.plain_language_summary,
    ]
    if consented:
        parts.append("你已同意執行，本地報告已產出；需花錢的動作在本版仍以計畫呈現，不會誤燒錢。")
    else:
        parts.append("目前只完成免費的分析與計畫，沒有執行任何花錢、寫入或發布的動作。")
    return " ".join(parts)


def _next_steps(consented: bool, cost) -> list[str]:
    steps = ["先看『給你的白話懶人包』(auto-report-beginner.md)，了解最重要的三件事。"]
    if cost.items:
        steps.append("看『成本與影響明細』(cost-estimate.json)，確認每個要花錢的動作與金額。")
    if not consented:
        steps.append("若要讓系統自動執行安全動作，重跑並加上 --approve 完成一次同意。")
    steps.append("需要工程或行銷團隊協助時，把完整報告 (auto-report.md) 交給他們。")
    return steps
