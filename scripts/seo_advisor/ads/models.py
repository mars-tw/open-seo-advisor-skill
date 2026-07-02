"""Meta 廣告優化專家（Meta Ads Mode）的資料模型，含動用預算的安全防護。

金額一律用「最小貨幣單位」的整數（minor units，例如 TWD 的分、Meta API 的
整數金額單位），避免 float 精度問題導致預算計算誤差。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class AdEntityStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DELETED = "DELETED"
    ARCHIVED = "ARCHIVED"


class AdsActionType(str, Enum):
    PAUSE_AD = "pause_ad"
    PAUSE_ADSET = "pause_adset"
    DECREASE_DAILY_BUDGET = "decrease_daily_budget"
    INCREASE_DAILY_BUDGET = "increase_daily_budget"
    DUPLICATE_ADSET = "duplicate_adset"
    CREATE_AD = "create_ad"
    ACTIVATE_ENTITY = "activate_entity"
    PAUSE_CAMPAIGN = "pause_campaign"


class AdsAccountProfile(BaseModel):
    account_id: str
    name: str = ""
    currency: str = "TWD"
    timezone: str = ""
    has_pixel: bool = False
    tracked_events: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class InsightsRow(BaseModel):
    """單一實體（ad/adset/campaign）在觀察期間的成效彙總。金額為 minor units。"""

    entity_id: str
    entity_type: str  # "campaign" | "adset" | "ad"
    name: str = ""
    status: AdEntityStatus = AdEntityStatus.ACTIVE
    spend_minor_units: int = 0
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    conversion_value_minor_units: int = 0
    frequency: float = 0.0
    daily_budget_minor_units: int | None = None
    days_active: int = 0

    @property
    def ctr(self) -> float:
        return (self.clicks / self.impressions) if self.impressions else 0.0

    @property
    def cpa_minor_units(self) -> float:
        return (self.spend_minor_units / self.conversions) if self.conversions else float("inf")

    @property
    def roas(self) -> float:
        return (
            self.conversion_value_minor_units / self.spend_minor_units
            if self.spend_minor_units
            else 0.0
        )


class AdsSafetyPolicy(BaseModel):
    """Meta 廣告代操的安全防護。所有會動用真實預算或改變投放狀態的操作，
    都必須通過這裡的檢查。預設值刻意保守——MVP 階段一律禁止「增加預算」與
    「啟用投放」這類會擴大花費的動作，需要使用者明確逐項開啟。
    """

    dry_run: bool = True
    allowed_ad_accounts: list[str] = Field(default_factory=list)
    allowed_capabilities: set[str] = Field(default_factory=lambda: {"ads_read"})

    require_apply_confirmation: bool = True
    require_budget_confirmation: bool = True

    max_actions_per_run: int = 10
    max_pause_ads_per_run: int = 20

    # MVP 一律禁止的高風險動作（會擴大花費或恢復投放）
    allow_campaign_pause: bool = False
    allow_activate_entities: bool = False
    allow_budget_increase: bool = False

    # 預算變更的多重上限（即使開啟增加預算，也受這些上限約束）
    max_budget_change_percent_per_entity: float = 0.15
    max_budget_change_minor_units_per_entity: int = 5000
    max_total_budget_delta_minor_units_per_run: int = 10000

    # 決策門檻：資料量不足時不建議動作，避免根據雜訊做決定
    min_observation_days: int = 7
    min_spend_minor_units_for_decision: int = 1000

    rollback_log_required: bool = True

    def require_account_allowed(self, account_id: str) -> None:
        if self.allowed_ad_accounts and account_id not in self.allowed_ad_accounts:
            raise PermissionError(
                f"廣告帳戶 {account_id} 不在允許清單中，拒絕操作。"
                "請在 AdsSafetyPolicy.allowed_ad_accounts 中明確加入這個帳戶。"
            )

    def require_capability(self, capability: str) -> None:
        if capability not in self.allowed_capabilities:
            raise PermissionError(
                f"此操作需要 '{capability}' 能力，但目前只允許：{sorted(self.allowed_capabilities)}。"
            )

    def require_action_allowed(self, action_type: AdsActionType) -> None:
        """檢查特定動作類型是否被政策允許（高風險動作預設禁止）。"""
        if action_type == AdsActionType.INCREASE_DAILY_BUDGET and not self.allow_budget_increase:
            raise PermissionError(
                "增加每日預算屬於高風險動作，MVP 預設禁止。"
                "如確定要開啟，需將 AdsSafetyPolicy.allow_budget_increase 設為 True。"
            )
        if action_type == AdsActionType.ACTIVATE_ENTITY and not self.allow_activate_entities:
            raise PermissionError(
                "啟用（恢復投放）屬於高風險動作，MVP 預設禁止。"
                "如確定要開啟，需將 AdsSafetyPolicy.allow_activate_entities 設為 True。"
            )
        if action_type == AdsActionType.PAUSE_CAMPAIGN and not self.allow_campaign_pause:
            raise PermissionError(
                "暫停整個活動屬於高風險動作，MVP 預設禁止。"
                "如確定要開啟，需將 AdsSafetyPolicy.allow_campaign_pause 設為 True。"
            )

    def require_write_not_dry_run(self) -> None:
        if self.dry_run:
            raise PermissionError(
                "目前處於 dry_run 模式，拒絕實際寫入 Meta 帳戶。"
                "請先檢視 action-plan.json，確認無誤後再以非 dry-run 模式套用。"
            )


class AdsAction(BaseModel):
    action_id: str
    type: AdsActionType
    entity_type: str
    entity_id: str
    entity_name: str = ""
    before: dict = Field(default_factory=dict)
    after: dict = Field(default_factory=dict)
    budget_delta_minor_units: int = 0
    risk_level: str = "P2"  # 沿用 P0-P3
    reason: str = ""
    rollback_snapshot: dict = Field(default_factory=dict)


class AdsActionPlan(BaseModel):
    plan_id: str
    account_id: str
    dry_run: bool = True
    generated_at: str
    currency: str = "TWD"
    actions: list[AdsAction] = Field(default_factory=list)
    total_budget_delta_minor_units: int = 0
    required_confirmation: str = ""
    rollback_required: bool = True


class AdsFinding(BaseModel):
    id: str
    title: str
    category: str  # tracking / structure / budget / creative_fatigue / audience / performance
    severity: str  # P0-P3
    entity_ids: list[str] = Field(default_factory=list)
    evidence: dict = Field(default_factory=dict)
    recommendation: str
    suggested_action_type: AdsActionType | None = None


class AdsReport(BaseModel):
    report_id: str
    generated_at: str
    account: AdsAccountProfile
    account_health_score: float = Field(ge=0, le=100)
    executive_summary: str
    findings: list[AdsFinding] = Field(default_factory=list)
    observation_days: int = 30
