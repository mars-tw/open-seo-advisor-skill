"""Mock 成效分析 provider：不需要 Google 憑證，供 demo 與測試。

假資料刻意涵蓋四種可診斷情境：高成本低轉換（預算浪費）、高流量低轉換率
（落地頁/受眾問題）、高轉換率低流量（可擴量）、有流量但零轉換（追蹤缺漏）。
"""

from __future__ import annotations

from seo_advisor.growth.models import AnalyticsMetricRow, AnalyticsSource
from seo_advisor.growth.providers.base import AnalyticsProvider


class MockAnalyticsProvider(AnalyticsProvider):
    def id(self) -> str:
        return "mock"

    def fetch_metrics(self, property_id: str, since_days: int) -> list[AnalyticsMetricRow]:
        return [
            AnalyticsMetricRow(
                channel="google_paid_high_cost",
                source=AnalyticsSource.MOCK,
                sessions=520,
                users=460,
                conversions=3,
                cost_minor_units=180_000,
                revenue_minor_units=20_000,
                clicks=610,
                impressions=18_000,
            ),
            AnalyticsMetricRow(
                channel="instagram_high_traffic_low_cvr",
                source=AnalyticsSource.MOCK,
                sessions=2_400,
                users=2_100,
                conversions=8,
                cost_minor_units=45_000,
                revenue_minor_units=12_000,
                clicks=2_900,
                impressions=120_000,
            ),
            AnalyticsMetricRow(
                channel="email_high_cvr_low_traffic",
                source=AnalyticsSource.MOCK,
                sessions=180,
                users=150,
                conversions=18,
                cost_minor_units=None,
                revenue_minor_units=90_000,
                clicks=220,
                impressions=1_500,
            ),
            AnalyticsMetricRow(
                channel="line_tracking_gap",
                source=AnalyticsSource.MOCK,
                sessions=760,
                users=690,
                conversions=0,
                cost_minor_units=None,
                revenue_minor_units=None,
                clicks=810,
                impressions=9_500,
            ),
            AnalyticsMetricRow(
                channel="organic_search_baseline",
                source=AnalyticsSource.MOCK,
                sessions=1_300,
                users=1_050,
                conversions=42,
                cost_minor_units=None,
                revenue_minor_units=210_000,
                clicks=1_100,
                impressions=22_000,
            ),
        ]
