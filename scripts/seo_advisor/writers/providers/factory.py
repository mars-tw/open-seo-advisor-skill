"""依名稱建立對應的 LLMProvider 實例，讓 CLI 只需要傳一個字串就能切換供應商。"""

from __future__ import annotations

from seo_advisor.writers.providers.base import LLMProvider, LLMProviderError

_PROVIDER_NAMES = {"anthropic", "openai", "local", "mock"}


def create_provider(name: str, *, model: str | None = None) -> LLMProvider:
    key = name.strip().lower()

    if key == "anthropic":
        from seo_advisor.writers.providers.anthropic import AnthropicProvider

        return AnthropicProvider(model=model) if model else AnthropicProvider()

    if key == "openai":
        from seo_advisor.writers.providers.openai import OpenAIProvider

        return OpenAIProvider(model=model) if model else OpenAIProvider()

    if key == "local":
        from seo_advisor.writers.providers.local import LocalProvider

        return LocalProvider(model=model) if model else LocalProvider()

    if key == "mock":
        from seo_advisor.writers.providers.mock import MockProvider

        return MockProvider()

    raise LLMProviderError(
        f"不支援的 LLM provider：{name!r}，可用選項：{sorted(_PROVIDER_NAMES)}"
    )
