"""依名稱建立對應的 ImageProvider 實例。"""

from __future__ import annotations

from seo_advisor.images.providers.base import ImageProvider, ImageProviderError

_PROVIDER_NAMES = {"openai", "mock"}


def create_image_provider(name: str, *, model: str | None = None) -> ImageProvider:
    key = name.strip().lower()

    if key == "openai":
        from seo_advisor.images.providers.openai import OpenAIImageProvider

        return OpenAIImageProvider(model=model)

    if key == "mock":
        from seo_advisor.images.providers.mock import MockImageProvider

        return MockImageProvider()

    raise ImageProviderError(
        f"不支援的圖像 provider：{name!r}，可用選項：{sorted(_PROVIDER_NAMES)}"
    )
