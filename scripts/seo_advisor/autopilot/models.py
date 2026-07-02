"""一鍵代操機器人（autopilot）的資料模型。

核心是「一次知情同意」：先自動跑完所有分析，把會花錢/寫入/發布的動作彙整
成白話成本明細（CostEstimate），使用者看懂、同意一次後才執行——而且同意
不是無限授權，只執行已列明細、已估風險、且在白名單內的動作。
"""

from __future__ import annotations

from enum import Enum

from typing import Literal

from pydantic import BaseModel, Field


class CostCategory(str, Enum):
    AD_SPEND = "ad_spend"  # 廣告花費
    API_USAGE = "api_usage"  # LLM/產圖等 API 費用
    WRITE = "write"  # 寫入檔案/設定
    PUBLISH = "publish"  # 對外發布
    INFRA = "infra"  # 伺服器/升級
    UNKNOWN = "unknown"  # 無法估算


class EstimateConfidence(str, Enum):
    FIXED = "fixed"  # 固定、可精確得知
    ESTIMATED = "estimated"  # 預估值
    UNKNOWN = "unknown"  # 無法估算


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CostEstimateItem(BaseModel):
    action_id: str
    module: str
    action_summary: str
    category: CostCategory
    amount_minor_units: int | None = None  # 金額（最小貨幣單位）
    currency: str | None = None
    token_estimate: int | None = None  # LLM/產圖的 token 估算
    unit_notes: str = ""
    confidence: EstimateConfidence = EstimateConfidence.ESTIMATED
    risk_level: RiskLevel
    reversible: bool
    rollback_summary: str | None = None
    user_facing_explanation: str
    execution_allowed_after_consent: bool


class CostEstimate(BaseModel):
    estimate_id: str
    generated_at: str
    dry_run: bool = True
    total_known_minor_units: int = 0
    currency: str | None = None
    items: list[CostEstimateItem] = Field(default_factory=list)
    unknown_cost_items: list[str] = Field(default_factory=list)
    max_authorized_minor_units: int | None = None
    plain_language_summary: str = ""


# 模組這次是「怎麼跑出來的」，如實標示避免讓使用者以為 mock 是真實掃描。
ExecutionMode = Literal["真實掃描", "純邏輯", "mock", "plan-only"]


class ModuleResult(BaseModel):
    """單一被 autopilot 呼叫的模組的結果摘要。"""

    module: str
    summary: str
    execution_mode: ExecutionMode = "純邏輯"
    report_paths: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)


class AutoTask(BaseModel):
    target: str  # 網址或目標描述
    industry: str | None = None
    locale: str = "zh-TW"
    mock: bool = False


class ExecutedAction(BaseModel):
    action_id: str
    module: str
    summary: str
    status: str  # executed | skipped_not_consented | skipped_blocklisted | plan_only
    detail: str = ""


class AutopilotDeliverable(BaseModel):
    deliverable_id: str
    generated_at: str
    target: str
    modules_run: list[str] = Field(default_factory=list)
    module_results: list[ModuleResult] = Field(default_factory=list)
    cost_estimate: CostEstimate
    consented: bool = False
    executed_actions: list[ExecutedAction] = Field(default_factory=list)
    executive_summary: str = ""
    next_steps: list[str] = Field(default_factory=list)
