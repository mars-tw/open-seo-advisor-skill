"""派工規劃：把 router 選出的角色轉成 Assignment，並套用安全升級。"""

from __future__ import annotations

from seo_advisor.matrix.models import Assignment, TaskRequest
from seo_advisor.matrix.registry import get_role
from seo_advisor.matrix.router import apply_safety_gate


def build_assignments(task: TaskRequest, role_ids: list[str]) -> list[Assignment]:
    assignments: list[Assignment] = []
    for i, role_id in enumerate(role_ids, start=1):
        role = get_role(role_id)
        if role is None:
            continue

        human_review, write_policy = apply_safety_gate(role, task)
        assignments.append(
            Assignment(
                assignment_id=f"{task.task_id}-a{i:02d}",
                task_id=task.task_id,
                role_id=role_id,
                engine=role.default_engine,
                reason=role.mission,
                inputs={
                    "user_goal": task.user_goal,
                    "industry": task.industry,
                    "write_policy": write_policy.value,
                },
                expected_outputs=role.capabilities,
                safety_notes=role.safety_notes,
                human_review_required=human_review,
            )
        )
    return assignments
