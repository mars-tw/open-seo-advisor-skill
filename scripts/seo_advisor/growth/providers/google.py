"""Google 成效資料來源（GA4 / Search Console / Google Ads）的 read-only adapter 骨架。

這三個來源各自需要不同的 Google SDK 與 OAuth 認證，屬於需要認證的重工。
本版先提供一致的建構檢查（憑證環境變數 + 選配 SDK），實際 API 呼叫規劃於
後續版本。無憑證時請改用 mock provider（`--provider mock`）即可完整試玩。

安全：這些 adapter 一律 read-only，即使是 Google Ads 也只讀取成效指標，
絕不修改任何廣告設定或預算。
"""

from __future__ import annotations

import os

from seo_advisor.growth.models import AnalyticsMetricRow
from seo_advisor.growth.providers.base import AnalyticsProvider, AnalyticsProviderError

_NOT_YET = (
    "尚未在此版本實作真實 Google API 呼叫（需要 OAuth 認證的重工）。"
    "目前請改用 --provider mock 完整試玩成效分析；真實 {name} 整合規劃於後續版本。"
)


class GA4AnalyticsProvider(AnalyticsProvider):
    def __init__(self) -> None:
        if not os.environ.get("GA4_PROPERTY_ID"):
            raise AnalyticsProviderError(
                "找不到環境變數 GA4_PROPERTY_ID，無法連接 GA4 Data API。"
                "無憑證時請改用 --provider mock。"
            )

    def id(self) -> str:
        return "ga4"

    def fetch_metrics(self, property_id: str, since_days: int) -> list[AnalyticsMetricRow]:
        raise AnalyticsProviderError(_NOT_YET.format(name="GA4"))


class SearchConsoleAnalyticsProvider(AnalyticsProvider):
    def __init__(self) -> None:
        if not os.environ.get("GSC_SITE_URL"):
            raise AnalyticsProviderError(
                "找不到環境變數 GSC_SITE_URL，無法連接 Search Console API。"
                "無憑證時請改用 --provider mock。"
            )

    def id(self) -> str:
        return "search_console"

    def fetch_metrics(self, property_id: str, since_days: int) -> list[AnalyticsMetricRow]:
        raise AnalyticsProviderError(_NOT_YET.format(name="Search Console"))


class GoogleAdsAnalyticsProvider(AnalyticsProvider):
    def __init__(self) -> None:
        if not os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN"):
            raise AnalyticsProviderError(
                "找不到環境變數 GOOGLE_ADS_DEVELOPER_TOKEN，無法連接 Google Ads API。"
                "無憑證時請改用 --provider mock。"
            )

    def id(self) -> str:
        return "google_ads"

    def fetch_metrics(self, property_id: str, since_days: int) -> list[AnalyticsMetricRow]:
        # read-only：即使實作了也只讀成效，不修改任何廣告設定或預算
        raise AnalyticsProviderError(_NOT_YET.format(name="Google Ads"))
