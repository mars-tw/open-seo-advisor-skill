"""Provider 與模組工廠的失敗路徑測試：確保缺金鑰、未知名稱、格式錯誤等
情境都給出清楚的錯誤，而不是靜默失敗或未處理的例外。
"""

import pytest


# --- 各 factory 對未知 provider 名稱都要拋出明確錯誤 ---

def test_llm_factory_unknown_raises():
    from seo_advisor.writers.providers.base import LLMProviderError
    from seo_advisor.writers.providers.factory import create_provider

    with pytest.raises(LLMProviderError):
        create_provider("nope")


def test_image_factory_unknown_raises():
    from seo_advisor.images.providers.base import ImageProviderError
    from seo_advisor.images.providers.factory import create_image_provider

    with pytest.raises(ImageProviderError):
        create_image_provider("nope")


def test_ads_factory_unknown_raises():
    from seo_advisor.ads.providers.base import AdsProviderError
    from seo_advisor.ads.providers.factory import create_ads_provider

    with pytest.raises(AdsProviderError):
        create_ads_provider("nope")


def test_analytics_factory_unknown_raises():
    from seo_advisor.growth.providers.base import AnalyticsProviderError
    from seo_advisor.growth.providers.factory import create_analytics_provider

    with pytest.raises(AnalyticsProviderError):
        create_analytics_provider("nope")


# --- 缺金鑰的 provider 要拋出帶「請設定環境變數」的清楚訊息 ---

def test_anthropic_missing_key_message(monkeypatch):
    from seo_advisor.writers.providers.base import LLMProviderError
    from seo_advisor.writers.providers.factory import create_provider

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMProviderError) as exc:
        create_provider("anthropic")
    assert "ANTHROPIC_API_KEY" in str(exc.value)


def test_openai_image_missing_key_message(monkeypatch):
    from seo_advisor.images.providers.base import ImageProviderError
    from seo_advisor.images.providers.factory import create_image_provider

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ImageProviderError) as exc:
        create_image_provider("openai")
    assert "OPENAI_API_KEY" in str(exc.value)


def test_meta_ads_missing_token_message(monkeypatch):
    from seo_advisor.ads.providers.base import AdsProviderError
    from seo_advisor.ads.providers.factory import create_ads_provider

    monkeypatch.delenv("META_ACCESS_TOKEN", raising=False)
    with pytest.raises(AdsProviderError) as exc:
        create_ads_provider("meta")
    assert "META_ACCESS_TOKEN" in str(exc.value)


def test_ga4_missing_property_message(monkeypatch):
    from seo_advisor.growth.providers.base import AnalyticsProviderError
    from seo_advisor.growth.providers.factory import create_analytics_provider

    monkeypatch.delenv("GA4_PROPERTY_ID", raising=False)
    with pytest.raises(AnalyticsProviderError) as exc:
        create_analytics_provider("ga4")
    assert "GA4_PROPERTY_ID" in str(exc.value)


# --- LLM 回傳非 JSON 時要拋出清楚錯誤（而非 KeyError / 崩潰） ---

def test_llm_malformed_json_raises_provider_error():
    from seo_advisor.writers.models import LLMMessage, LLMRequest
    from seo_advisor.writers.providers.base import LLMProviderError
    from seo_advisor.writers.providers.mock import MockProvider

    provider = MockProvider("這不是 JSON，是一段普通文字")
    req = LLMRequest(system="s", messages=[LLMMessage(role="user", content="hi")])
    with pytest.raises(LLMProviderError):
        provider.complete_json(req, schema={"type": "object"})


# --- Meta Ads 的實際代操在本版一律被擋（不論是否有 token） ---

def test_meta_ads_apply_is_blocked(monkeypatch):
    from seo_advisor.ads.providers.base import AdsProviderError
    from seo_advisor.ads.providers.mock import MockAdsProvider

    provider = MockAdsProvider()
    with pytest.raises(AdsProviderError):
        provider.apply_actions(plan=None, confirmation="x")
