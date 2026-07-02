"""依名稱建立對應的 AdsProvider 實例。"""

from __future__ import annotations

from seo_advisor.ads.providers.base import AdsProvider, AdsProviderError

_PROVIDER_NAMES = {"meta", "mock"}


def create_ads_provider(name: str) -> AdsProvider:
    key = name.strip().lower()

    if key == "meta":
        from seo_advisor.ads.providers.meta import MetaAdsProvider

        return MetaAdsProvider()

    if key == "mock":
        from seo_advisor.ads.providers.mock import MockAdsProvider

        return MockAdsProvider()

    raise AdsProviderError(
        f"不支援的廣告 provider：{name!r}，可用選項：{sorted(_PROVIDER_NAMES)}"
    )
