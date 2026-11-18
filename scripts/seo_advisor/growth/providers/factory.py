"""依名稱建立對應的 AnalyticsProvider。"""

from __future__ import annotations

from seo_advisor.growth.providers.base import AnalyticsProvider, AnalyticsProviderError

def create_analytics_provider(name: str) -> AnalyticsProvider:
    key = name.strip().lower()

    if key == "mock":
        from seo_advisor.growth.providers.mock import MockAnalyticsProvider

        return MockAnalyticsProvider()

    if key == "ga4":
        from seo_advisor.growth.providers.google import GA4AnalyticsProvider

        return GA4AnalyticsProvider()

    if key == "search_console":
        from seo_advisor.growth.providers.google import SearchConsoleAnalyticsProvider

        return SearchConsoleAnalyticsProvider()

    if key == "google_ads":
        from seo_advisor.growth.providers.google import GoogleAdsAnalyticsProvider

        return GoogleAdsAnalyticsProvider()

    raise AnalyticsProviderError(
        f"不支援的成效分析 provider：{name!r}，目前可用 mock。"
    )
