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
from seo_advisor.autopilot.report import (
    render_autopilot_beginner_md,
    render_autopilot_md,
    render_cost_estimate_md,
)
from seo_advisor.url_utils import looks_like_url

ProgressCallback = Callable[[str], None]

# MVP 安全開關：為真時，所有會花錢/寫入/發布的動作一律只產計畫、不自動執行，
# 成本明細也以「示範、不會真的花錢」呈現，確保現階段絕不誤燒錢。未來開放真實
# 執行時改為 False，屆時真實成本會依 task.mock 正確標示（不再被強制標成 mock）。
_MVP_FORCE_PLAN_ONLY = True


@dataclass
class AutopilotOutcome:
    deliverable: AutopilotDeliverable
    beginner_path: Path
    report_path: Path
    json_path: Path
    cost_estimate_path: Path  # JSON（給自動化）
    cost_estimate_md_path: Path  # Markdown（給人看）


def _noop(_: str) -> None:
    return None


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def select_modules(task: AutoTask) -> list[str]:
    """依目標自動判斷要跑哪些模組。"""
    text = (task.target + " " + (task.industry or "")).lower()
    modules: list[str] = []

    # 用 url_utils.looks_like_url：新手直接打 example.com（沒有 https://）也能
    # 被正確當成網址，不會被誤判成「模糊目標」而跑錯模組。
    if looks_like_url(task.target):
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

    on_progress("第 2/5 步：各專家開始分析（若含網址會實際做一次快速 SEO 健檢）")
    module_results = _run_module_analyses(task, modules, out_dir)

    on_progress("第 3/5 步：彙整成本與影響明細")
    plan_image = 4 if "image_plan" in modules else 0
    plan_content = 2 if "content_plan" in modules else 0
    # 成本明細是否以「示範/不花錢」呈現：MVP 階段強制為真（真實花錢動作一律
    # 停在計畫，見 _MVP_FORCE_PLAN_ONLY），或使用者明確指定 --mock。
    # 未來開放真實執行時，只要把 _MVP_FORCE_PLAN_ONLY 設 False，task.mock 就會
    # 正確生效、真實成本不會再被誤標成 mock。
    cost_as_mock = _MVP_FORCE_PLAN_ONLY or task.mock
    cost = build_cost_estimate(
        estimate_id=f"cost-{generated_at[:10]}",
        generated_at=generated_at,
        plan_image_variants=plan_image,
        plan_content_pieces=plan_content,
        plan_ad_budget_delta_minor_units=0,
        mock=cost_as_mock,
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
        executive_summary=_summary_from_estimate(task.target, modules, cost, consented),
        next_steps=_next_steps(consented, cost),
    )

    on_progress("第 5/5 步：輸出報告")
    return _write_outcome(deliverable, out_dir)


def _write_outcome(deliverable: AutopilotDeliverable, out_dir: str) -> AutopilotOutcome:
    """把交付物寫成報告檔並回傳 outcome。供首次分析與同意後重寫共用。"""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    beginner_path = out_path / "auto-report-beginner.md"
    report_path = out_path / "auto-report.md"
    json_path = out_path / "auto-report.json"
    cost_path = out_path / "cost-estimate.json"
    cost_md_path = out_path / "cost-estimate.md"

    beginner_path.write_text(render_autopilot_beginner_md(deliverable), encoding="utf-8")
    report_path.write_text(render_autopilot_md(deliverable), encoding="utf-8")
    json_path.write_text(
        json.dumps(deliverable.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    cost_path.write_text(
        json.dumps(deliverable.cost_estimate.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    cost_md_path.write_text(render_cost_estimate_md(deliverable.cost_estimate), encoding="utf-8")

    return AutopilotOutcome(
        deliverable=deliverable,
        beginner_path=beginner_path,
        report_path=report_path,
        json_path=json_path,
        cost_estimate_path=cost_path,
        cost_estimate_md_path=cost_md_path,
    )


def apply_consent(outcome: AutopilotOutcome, out_dir: str) -> AutopilotOutcome:
    """使用者同意後，用**同一份**已分析的交付物更新同意狀態並重寫報告——
    不重跑分析，確保執行的正是使用者剛剛看過並同意的那份計畫。
    """
    d = outcome.deliverable
    updated = d.model_copy(
        update={
            "consented": True,
            "executed_actions": _execute_safe_actions(d.module_results, consented=True),
            "executive_summary": _summary_from_estimate(d.target, d.modules_run, d.cost_estimate, True),
            "next_steps": _next_steps(True, d.cost_estimate),
        }
    )
    return _write_outcome(updated, out_dir)


def _run_module_analyses(task: AutoTask, modules: list[str], out_dir: str) -> list[ModuleResult]:
    results: list[ModuleResult] = []
    for module in modules:
        results.append(_run_one_module(task, module, out_dir))
    return results


def _relpath(path, out_dir: str) -> str:
    """把絕對路徑轉成相對 out_dir 的路徑，避免對外報告洩漏本機使用者名稱。"""
    try:
        return str(Path(path).relative_to(Path(out_dir)))
    except ValueError:
        return Path(path).name


def _run_consultant(task: AutoTask, out_dir: str) -> ModuleResult:
    """真的跑一次 Consultant 健檢（唯讀、免費、安全）。失敗時降級為 failed
    module 但不讓 autopilot 整體崩潰——其他分析照常。
    """
    from seo_advisor.demo import run_demo_scan
    from seo_advisor.errors import redact_secrets, translate_exception
    from seo_advisor.scan_runner import run_consultant_scan

    module_out = str(Path(out_dir) / "consultant")
    try:
        if task.mock:
            outcome = run_demo_scan(out_dir=module_out)
            mode = "mock"
        else:
            # autopilot 用較小範圍與較短 timeout 求快速出結果，慢站會快速失敗
            # 降級而非拖垮整體；要深掃引導用完整指令。
            outcome = run_consultant_scan(
                url=task.target, source=None, out_dir=module_out,
                max_urls=30, max_depth=3, timeout_seconds=8.0,
            )
            mode = "真實掃描"
        report = outcome.report
        return ModuleResult(
            module="consultant",
            summary=(
                f"已完成 SEO 健檢：健康分數 {report.site_health_score:.0f}/100，"
                f"發現 {len(report.findings)} 個問題（快速健檢）。"
            ),
            execution_mode=mode,
            highlights=[
                f"健康分數：{report.site_health_score:.0f}/100",
                f"問題數：{len(report.findings)}",
            ],
            advanced_hint="想更深入掃描：seo-advisor audit consultant --max-urls 200",
            # 對外只放相對路徑（相對 out_dir），避免絕對路徑洩漏本機使用者名稱。
            report_paths=[
                _relpath(outcome.beginner_path, out_dir),
                _relpath(outcome.technical_path, out_dir),
                _relpath(outcome.json_path, out_dir),
            ],
        )
    except Exception as exc:  # noqa: BLE001 - 單一模組失敗不該讓 autopilot 整體崩
        reason = redact_secrets(translate_exception(exc).title)
        return ModuleResult(
            module="consultant",
            summary="SEO 健檢沒有完成：網站連線或安全檢查未通過，其他分析已照常進行。",
            execution_mode="failed",
            highlights=[f"原因：{reason}", "建議：先確認這個網址在瀏覽器能正常打開。"],
            advanced_hint="想看失敗細節：seo-advisor audit consultant --url <你的網址> --debug",
        )


def _run_one_module(task: AutoTask, module: str, out_dir: str) -> ModuleResult:
    # consultant 是唯讀、免費、安全的分析，直接真跑；其餘模組目前仍提供方向與
    # 計畫（會花錢/寫入的動作受成本明細與同意閘門控制，見 build_cost_estimate）。
    if module == "consultant":
        return _run_consultant(task, out_dir)
    if module == "ecommerce":
        return ModuleResult(
            module="ecommerce",
            summary="已規劃電商 listing 檢核方向（標題/賣點/圖片/評論/庫存等）。",
            execution_mode="plan-only",
            highlights=["列出該檢查的 listing 項目"],
            advanced_hint="想做完整電商健檢：seo-advisor ecommerce audit",
        )
    if module in {"growth_cro", "growth_utm", "growth_analytics"}:
        label = {"growth_cro": "落地頁 CRO", "growth_utm": "UTM 歸因", "growth_analytics": "跨渠道成效"}[module]
        return ModuleResult(
            module=module,
            summary=f"已規劃「{label}」方向。",
            execution_mode="plan-only",
            highlights=[f"{label}建議方向已產出"],
            advanced_hint="想做完整成長分析：seo-advisor growth",
        )
    if module == "content_plan":
        return ModuleResult(
            module="content_plan",
            summary="已規劃內容方向（實際產文需 LLM 金鑰，屬同意後才執行的動作）。",
            execution_mode="plan-only",
            highlights=["內容主題與大綱建議"],
        )
    if module == "image_plan":
        return ModuleResult(
            module="image_plan",
            summary="已規劃素材方向（實際產圖需 API，屬同意後才執行的動作）。",
            execution_mode="plan-only",
            highlights=["素材版位與變體建議"],
        )
    return ModuleResult(
        module="matrix",
        summary="已由 NORA 總控判斷並規劃跨領域成長方案骨架。",
        execution_mode="plan-only",
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


def _summary_from_estimate(target: str, modules: list[str], cost, consented: bool) -> str:
    parts = [
        f"針對「{target}」，一鍵顧問已自動出動 {len(modules)} 位專家完成分析，"
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
