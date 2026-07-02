"""成效分析 provider：GA4 / Search Console / Google Ads（read-only）/ Mock。"""

from seo_advisor.growth.providers.base import AnalyticsProvider, AnalyticsProviderError
from seo_advisor.growth.providers.factory import create_analytics_provider

__all__ = ["AnalyticsProvider", "AnalyticsProviderError", "create_analytics_provider"]
