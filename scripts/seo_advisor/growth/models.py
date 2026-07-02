"""成長行銷模型：UTM 歸因、CRO 落地頁優化、跨渠道成效分析。

補齊網路行銷團隊該有、但先前專案缺少的能力（歸因追蹤、轉換率優化、
成效分析）。UTM 與 CRO 純邏輯即可運作；成效分析的資料來源（GA4/GSC/
Google Ads）為 optional read-only adapter，無金鑰時用 mock 即可完整試玩。
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from seo_advisor.models import Severity

CroCategory = Literal["structure", "cta", "form", "message_match", "trust", "speed_hint"]


class UtmParams(BaseModel):
    source: str
    medium: str
    campaign: str
    term: str | None = None
    content: str | None = None


class UtmAuditItem(BaseModel):
    url: str
    severity: Severity = Severity.P2
    issue_code: str
    field: str | None = None
    message: str
    recommendation: str


class UtmPlan(BaseModel):
    base_url: str
    channels: list[str] = Field(default_factory=list)
    tagged_urls: list[str] = Field(default_factory=list)
    params_by_channel: dict[str, UtmParams] = Field(default_factory=dict)
    naming_recommendations: list[str] = Field(default_factory=list)
    audit_items: list[UtmAuditItem] = Field(default_factory=list)


class CroFinding(BaseModel):
    category: CroCategory
    severity: Severity
    title: str
    evidence: str = ""
    recommendation: str


class AbTestIdea(BaseModel):
    element: str
    hypothesis: str
    variant_a: str
    variant_b: str
    primary_metric: str
    min_sample_hint: str


class CroReport(BaseModel):
    landing_url: str
    findings: list[CroFinding] = Field(default_factory=list)
    ab_test_ideas: list[AbTestIdea] = Field(default_factory=list)
    conversion_hypotheses: list[str] = Field(default_factory=list)


# --- 跨渠道成效分析（GA4 / Search Console / Google Ads，read-only） ---


class AnalyticsSource(str, Enum):
    GA4 = "ga4"
    SEARCH_CONSOLE = "search_console"
    GOOGLE_ADS = "google_ads"
    MOCK = "mock"


class AnalyticsMetricRow(BaseModel):
    """單一渠道/來源在觀察期間的成效彙總。金額為最小貨幣單位（minor units）。"""

    channel: str
    source: AnalyticsSource = AnalyticsSource.MOCK
    sessions: int = Field(default=0, ge=0)
    users: int = Field(default=0, ge=0)
    conversions: int = Field(default=0, ge=0)
    cost_minor_units: int | None = Field(default=None, ge=0)
    revenue_minor_units: int | None = Field(default=None, ge=0)
    clicks: int = Field(default=0, ge=0)
    impressions: int = Field(default=0, ge=0)

    @computed_field
    @property
    def conversion_rate(self) -> float:
        return round(self.conversions / self.sessions, 4) if self.sessions else 0.0

    @computed_field
    @property
    def ctr(self) -> float:
        return round(self.clicks / self.impressions, 4) if self.impressions else 0.0


class AnalyticsFinding(BaseModel):
    category: Literal["traffic", "conversion", "spend", "tracking"]
    severity: Severity
    title: str
    evidence: dict = Field(default_factory=dict)
    recommendation: str


class AnalyticsReport(BaseModel):
    source: AnalyticsSource
    property_id: str
    date_range: str
    rows: list[AnalyticsMetricRow] = Field(default_factory=list)
    findings: list[AnalyticsFinding] = Field(default_factory=list)
    summary: str = ""
