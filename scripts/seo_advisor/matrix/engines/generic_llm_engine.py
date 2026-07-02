"""GenericLLMEngine：沒有專屬引擎的角色，用 Content Writer 的 LLMProvider
抽象層 + 通用角色執行 prompt，產出結構化交付物。

無金鑰或呼叫失敗時 fallback 到 MockEngine，確保 matrix 流程能穩定跑完
（demo/CI 不會因為缺金鑰而中斷）。
"""

from __future__ import annotations

import importlib.resources

from seo_advisor.matrix.engines.base import Engine
from seo_advisor.matrix.engines.mock_engine import MockEngine
from seo_advisor.matrix.models import ActionItem, AgentRunResult, Assignment, HumanReviewFlag, TaskRequest
from seo_advisor.matrix.registry import get_role
from seo_advisor.writers.models import LLMMessage, LLMRequest
from seo_advisor.writers.providers.factory import create_provider

_PROMPT_PACKAGE = "seo_advisor.matrix.prompts"
_PROMPT_FILENAME = "generic_role_executor.md"

_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["summary", "action_items", "human_review_required"],
    "properties": {
        "summary": {"type": "string"},
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "description"],
                "properties": {
                    "priority": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
        "human_review_required": {"type": "boolean"},
        "review_notes": {"type": "array", "items": {"type": "string"}},
    },
}


def _load_prompt() -> str:
    traversable = importlib.resources.files(_PROMPT_PACKAGE) / _PROMPT_FILENAME
    with importlib.resources.as_file(traversable) as path:
        return path.read_text(encoding="utf-8")


def _build_user_payload(role, task: TaskRequest, assignment: Assignment) -> str:
    import json

    payload = {
        "role": {
            "display_name": role.display_name if role else assignment.role_id,
            "title": role.title if role else "",
            "mission": role.mission if role else "",
            "capabilities": role.capabilities if role else [],
            "write_policy": assignment.inputs.get("write_policy", ""),
        },
        "task": {
            "user_goal": task.user_goal,
            "industry": task.industry,
            "locale": task.locale,
            "business_context": task.business_context,
            "constraints": task.constraints,
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class GenericLLMEngine(Engine):
    def __init__(self, *, provider_name: str = "mock", model: str | None = None) -> None:
        self.provider_name = provider_name
        self.model = model

    def run(self, assignment: Assignment, task: TaskRequest) -> AgentRunResult:
        # mock provider 直接走 MockEngine（免金鑰的預設路徑）
        if self.provider_name == "mock":
            return MockEngine().run(assignment, task)

        role = get_role(assignment.role_id)
        try:
            provider = create_provider(self.provider_name, model=self.model)
            response = provider.complete_json(
                LLMRequest(
                    system=_load_prompt(),
                    messages=[
                        LLMMessage(role="user", content=_build_user_payload(role, task, assignment))
                    ],
                    temperature=0.2,
                    max_tokens=3000,
                ),
                _OUTPUT_SCHEMA,
            )
            payload = response.json_data or {}
        except Exception:  # noqa: BLE001 - matrix 流程需穩定降級，改用 mock 產出
            return MockEngine().run(assignment, task)

        action_items = [
            ActionItem(
                role_id=assignment.role_id,
                title=str(item.get("title", "未命名行動")),
                detail=str(item.get("description", "")),
                human_review_required=bool(item.get("human_review_required", False)),
            )
            for item in payload.get("action_items", [])
            if isinstance(item, dict)
        ]

        review_flags: list[HumanReviewFlag] = []
        for note in payload.get("review_notes", []) or []:
            review_flags.append(HumanReviewFlag(role_id=assignment.role_id, reason=str(note)))
        if payload.get("human_review_required") or assignment.human_review_required:
            review_flags.append(
                HumanReviewFlag(
                    role_id=assignment.role_id,
                    reason="此交付物涉及需人工確認的內容。",
                    severity="P1",
                )
            )

        return AgentRunResult(
            assignment_id=assignment.assignment_id,
            role_id=assignment.role_id,
            status="needs_review" if review_flags else "success",
            summary=str(payload.get("summary", "")).strip(),
            action_items=action_items,
            review_flags=review_flags,
        )
