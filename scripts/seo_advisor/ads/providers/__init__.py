"""AdsProvider 實作：讓廣告優化專家可切換 Meta / Mock。"""

from seo_advisor.ads.providers.base import AdsProvider, AdsProviderError
from seo_advisor.ads.providers.factory import create_ads_provider

__all__ = ["AdsProvider", "AdsProviderError", "create_ads_provider"]
