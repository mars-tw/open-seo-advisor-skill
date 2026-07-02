"""整合器：把各角色的執行結果整合成一份 MatrixDeliverable。"""

from __future__ import annotations

from seo_advisor.matrix.models import (
    ActionItem,
    AgentRunResult,
    Assignment,
    HumanReviewFlag,
    MatrixDeliverable,
    TaskRequest,
)


def synthesize(
    task: TaskRequest,
    assignments: list[Assignment],
    results: list[AgentRunResult],
    *,
    generated_at: str,
) -> MatrixDeliverable:
    integrated_plan: list[ActionItem] = []
    risks: list[HumanReviewFlag] = []
    for result in results:
        integrated_plan.extend(result.action_items)
        risks.extend(result.review_flags)

    human_review_required = any(a.human_review_required for a in assignments) or bool(risks)
    selected_roles = [a.role_id for a in assignments]

    summary = _build_summary(task, selected_roles, human_review_required, len(integrated_plan))
    next_steps = _build_next_steps(human_review_required)

    return MatrixDeliverable(
        deliverable_id=f"matrix-{task.task_id}",
        task_id=task.task_id,
        generated_at=generated_at,
        user_goal=task.user_goal,
        executive_summary=summary,
        selected_roles=selected_roles,
        assignments=assignments,
        role_results=results,
        integrated_plan=integrated_plan,
        risks=risks,
        human_review_required=human_review_required,
        next_steps=next_steps,
    )


def _build_summary(task, roles, human_review, action_count) -> str:
    role_names = "、".join(r.upper() for r in roles)
    parts = [
        f"針對目標「{task.user_goal}」，NORA 已啟用 {len(roles)} 位 AI 工作夥伴"
        f"（{role_names}），整合出 {action_count} 項具體行動。",
    ]
    if human_review:
        parts.append("其中包含需要人工確認的項目（例如預算、法務、財務或對外發布），"
                     "請先審核再執行。")
    return " ".join(parts)


def _build_next_steps(human_review: bool) -> list[str]:
    steps = [
        "檢視整合行動清單，確認優先順序與負責人。",
        "把各角色的建議轉為實際排程與交付物。",
    ]
    if human_review:
        steps.insert(0, "先處理標記為『需人工確認』的項目，尤其是涉及預算/法務/發布的部分。")
    return steps
