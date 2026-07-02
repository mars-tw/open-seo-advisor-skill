"""AI 矩陣營運系統（AI Matrix Operating System）的資料模型。

矩陣系統是「上層統籌層」：NORA 總控接收任務、判斷情境、派工給對應的 AI
工作夥伴角色，各角色透過 engine adapter 執行（盡量接到現有已實作的引擎——
Consultant / Content Writer / Meta Ads / Image Material——沒有現成引擎的角色
走 Generic LLM），最後整合成一份可執行交付物。

設計定案見 .collab-rules.md 的「AI 矩陣營運系統」一節（CLAUDE 與 NORA 協作）。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class EngineType(str, Enum):
    CONSULTANT = "consultant"
    CONTENT_WRITER = "content_writer"
    META_ADS = "meta_ads"
    IMAGE_MATERIAL = "image_material"
    GENERIC_LLM = "generic_llm"
    MOCK = "mock"


class WritePolicy(str, Enum):
    """角色可執行的寫入層級。任何會寫入/部署/花錢/發布的動作一律只產計畫。"""

    READ_ONLY = "read_only"  # 只讀取與分析
    GENERATE_ARTIFACTS_ONLY = "generate_artifacts_only"  # 只產出檔案素材（如產圖）
    PLAN_ONLY = "plan_only"  # 只產計畫，不實際執行（如廣告、部署）


class SafetyLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentRole(BaseModel):
    """AI 工作夥伴的角色卡（資料驅動，來自 assets/roles.yaml，不為每個角色寫 class）。"""

    id: str
    display_name: str
    title: str
    group: str = "general"
    mission: str = ""
    capabilities: list[str] = Field(default_factory=list)
    default_engine: EngineType = EngineType.GENERIC_LLM
    fallback_engine: EngineType = EngineType.GENERIC_LLM
    safety_level: SafetyLevel = SafetyLevel.MEDIUM
    human_review_required: bool = False
    write_policy: WritePolicy = WritePolicy.READ_ONLY
    safety_notes: list[str] = Field(default_factory=list)


class TaskRequest(BaseModel):
    """使用者對 NORA 下達的任務。"""

    task_id: str = "task"
    user_goal: str
    industry: str | None = None
    locale: str = "zh-TW"
    business_context: dict = Field(default_factory=dict)
    requested_roles: list[str] | None = None
    source_refs: list[str] = Field(default_factory=list)
    constraints: dict = Field(default_factory=dict)
    dry_run: bool = True


class Assignment(BaseModel):
    """NORA 把任務拆解後，指派給某個角色的工作單。"""

    assignment_id: str
    task_id: str
    role_id: str
    engine: EngineType
    reason: str = ""
    inputs: dict = Field(default_factory=dict)
    expected_outputs: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    human_review_required: bool = False


class HumanReviewFlag(BaseModel):
    role_id: str
    reason: str
    severity: str = "P2"  # 沿用 P0-P3


class ActionItem(BaseModel):
    role_id: str
    title: str
    detail: str = ""
    human_review_required: bool = False


class AgentRunResult(BaseModel):
    assignment_id: str
    role_id: str
    status: str = "success"  # success | needs_review | blocked | failed
    summary: str = ""
    artifacts: list[str] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    review_flags: list[HumanReviewFlag] = Field(default_factory=list)


class MatrixDeliverable(BaseModel):
    deliverable_id: str
    task_id: str
    generated_at: str
    user_goal: str
    executive_summary: str = ""
    selected_roles: list[str] = Field(default_factory=list)
    assignments: list[Assignment] = Field(default_factory=list)
    role_results: list[AgentRunResult] = Field(default_factory=list)
    integrated_plan: list[ActionItem] = Field(default_factory=list)
    risks: list[HumanReviewFlag] = Field(default_factory=list)
    human_review_required: bool = False
    next_steps: list[str] = Field(default_factory=list)
