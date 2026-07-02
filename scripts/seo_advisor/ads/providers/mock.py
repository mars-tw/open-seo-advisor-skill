"""MockAdsProvider：不需要 Meta API 金鑰，提供內含各種常見問題的假廣告帳戶資料，
讓 demo / audit / plan 流程能完整展示分析與診斷，不會呼叫任何真實 API、
也絕不會動用真實預算。
"""

from __future__ import annotations

from seo_advisor.ads.models import (
    AdEntityStatus,
    AdsAccountProfile,
    InsightsRow,
)
from seo_advisor.ads.providers.base import AdsProvider

# 刻意設計成包含多種可診斷問題的假資料：
# - ad_high_spend_low_roas：高花費低回報（預算浪費候選）
# - ad_fatigued：高 frequency + 低 CTR（素材疲勞）
# - ad_scaling_candidate：低花費高 ROAS（擴量候選）
# - adset_underfunded：資料量不足（觀察期太短）
_MOCK_INSIGHTS = [
    InsightsRow(
        entity_id="ad_1001",
        entity_type="ad",
        name="夏季促銷-圖A",
        status=AdEntityStatus.ACTIVE,
        spend_minor_units=800000,  # 8000 元
        impressions=200000,
        clicks=1800,
        conversions=8,
        conversion_value_minor_units=480000,  # ROAS 0.6，明顯虧損
        frequency=2.1,
        daily_budget_minor_units=None,
        days_active=21,
    ),
    InsightsRow(
        entity_id="ad_1002",
        entity_type="ad",
        name="夏季促銷-圖B（疲勞）",
        status=AdEntityStatus.ACTIVE,
        spend_minor_units=300000,
        impressions=500000,
        clicks=1200,  # CTR 0.24%，偏低
        conversions=15,
        conversion_value_minor_units=600000,
        frequency=7.8,  # 高頻次，素材疲勞
        daily_budget_minor_units=None,
        days_active=45,
    ),
    InsightsRow(
        entity_id="ad_1003",
        entity_type="ad",
        name="常青內容-圖C（擴量候選）",
        status=AdEntityStatus.ACTIVE,
        spend_minor_units=150000,  # 1500 元，花費低
        impressions=80000,
        clicks=1600,
        conversions=40,
        conversion_value_minor_units=1200000,  # ROAS 8.0，表現極佳
        frequency=1.6,
        daily_budget_minor_units=None,
        days_active=30,
    ),
    InsightsRow(
        entity_id="adset_2001",
        entity_type="adset",
        name="測試組-新受眾（資料不足）",
        status=AdEntityStatus.ACTIVE,
        spend_minor_units=40000,  # 花費過低，資料不足
        impressions=12000,
        clicks=90,
        conversions=1,
        conversion_value_minor_units=30000,
        frequency=1.2,
        daily_budget_minor_units=20000,
        days_active=3,  # 觀察期太短
    ),
]


class MockAdsProvider(AdsProvider):
    def id(self) -> str:
        return "mock"

    def capabilities(self) -> set[str]:
        # mock 明確標示只提供讀取能力，不會（也無法）真的寫入任何帳戶
        return {"ads_read"}

    def probe(self, account_id: str) -> AdsAccountProfile:
        return AdsAccountProfile(
            account_id=account_id,
            name="（示範）Mock 廣告帳戶",
            currency="TWD",
            timezone="Asia/Taipei",
            has_pixel=True,
            tracked_events=["PageView", "ViewContent", "Purchase"],
            notes=["這是 mock provider 的示範資料，並非真實廣告帳戶。"],
        )

    def fetch_insights(self, account_id: str, *, since_days: int) -> list[InsightsRow]:
        return list(_MOCK_INSIGHTS)
