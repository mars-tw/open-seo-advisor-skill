"""MockEngine：不需任何 API 金鑰，依角色產出固定但合理的結構化結果。

讓 `seo-advisor matrix demo` 在零金鑰下能完整跑完整條路由→派工→執行→整合
流程，也供測試與 CI 使用。輸出明確標示為示範資料。
"""

from __future__ import annotations

from seo_advisor.matrix.engines.base import Engine
from seo_advisor.matrix.models import ActionItem, AgentRunResult, Assignment, HumanReviewFlag, TaskRequest
from seo_advisor.matrix.registry import get_role

_ROLE_ACTIONS: dict[str, list[tuple[str, str, str]]] = {
    "iris": [
        ("P1", "執行 SEO 健檢", "檢查 sitemap、robots、canonical、title/H1 與內部連結。"),
        ("P1", "整理前三大 SEO 問題", "依影響程度排序並提出修正優先順序。"),
    ],
    "jack": [
        ("P0", "只產出廣告變更計畫", "涉及預算與投放，預設 dry-run，不直接套用。"),
        ("P1", "找出高花費低成效項目", "標出 CPA 高、ROAS 低或素材疲勞的廣告。"),
    ],
    "pixel": [
        ("P2", "規劃素材方向", "產出 1:1、9:16、16:9 素材變體與 prompt。"),
        ("P2", "標記合規注意事項", "避免誤導性素材、冒用品牌或未授權肖像。"),
    ],
    "cody": [
        ("P1", "設計銷售頁架構", "建立痛點、承諾、證據、CTA 與 FAQ 區塊。"),
    ],
    "maya": [
        ("P1", "規劃內容行事曆", "依平台特性排出一週貼文主題與 hook。"),
    ],
    "orion": [
        ("P1", "定義追蹤指標", "列出本任務應追蹤的 KPI、資料來源與報表欄位。"),
    ],
    "rina": [
        ("P1", "盤點現行流程", "找出重複、等待、交接與容易出錯的節點。"),
    ],
    "otto": [
        ("P2", "提出自動化候選", "列出可用 API、排程或 workflow 工具處理的工作。"),
    ],
    "lex": [
        ("P0", "標記法務覆核", "合約/條款/合規建議僅供整理，必須由專業人士覆核。"),
    ],
    "grace": [
        ("P0", "標記財務覆核", "財務數字、預算與預測不可直接作為決策依據。"),
    ],
}

_DEFAULT_ACTIONS = [
    ("P1", "釐清目標", "確認本次任務的主要 KPI、受眾與限制條件。"),
    ("P2", "建立執行清單", "把任務拆成 3-5 個可驗收的小步驟。"),
    ("P3", "安排覆核", "完成初稿後交由人工審核再採用。"),
]


class MockEngine(Engine):
    def run(self, assignment: Assignment, task: TaskRequest) -> AgentRunResult:
        role = get_role(assignment.role_id)
        display = role.display_name if role else assignment.role_id.upper()
        title = role.title if role else assignment.role_id

        summary = (
            f"{display}（{title}）已針對任務「{task.user_goal}」產出示範版建議。"
            "此結果由 MockEngine 產生，適合 demo 與測試，不代表真實外部資料分析。"
        )

        raw_actions = _ROLE_ACTIONS.get(assignment.role_id, _DEFAULT_ACTIONS)
        action_items = [
            ActionItem(
                role_id=assignment.role_id,
                title=title_,
                detail=detail,
                human_review_required=assignment.human_review_required,
            )
            for (_prio, title_, detail) in raw_actions
        ]

        review_flags: list[HumanReviewFlag] = []
        if assignment.human_review_required:
            review_flags.append(
                HumanReviewFlag(
                    role_id=assignment.role_id,
                    reason="此角色/任務涉及預算、法務、財務或對外發布，需人工確認。",
                    severity="P1",
                )
            )

        return AgentRunResult(
            assignment_id=assignment.assignment_id,
            role_id=assignment.role_id,
            status="needs_review" if review_flags else "success",
            summary=summary,
            action_items=action_items,
            review_flags=review_flags,
        )
