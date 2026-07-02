import pytest

from seo_advisor.writers.models import LLMMessage, LLMRequest
from seo_advisor.writers.providers.base import LLMProviderError
from seo_advisor.writers.providers.factory import create_provider
from seo_advisor.writers.providers.mock import MockProvider


def test_create_mock_provider():
    provider = create_provider("mock")
    assert isinstance(provider, MockProvider)
    assert provider.id() == "mock"


def test_create_unknown_provider_raises_friendly_error():
    with pytest.raises(LLMProviderError):
        create_provider("not-a-real-provider")


def test_anthropic_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMProviderError):
        create_provider("anthropic")


def test_openai_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(LLMProviderError):
        create_provider("openai")


def test_mock_provider_complete_returns_fixed_text():
    provider = MockProvider("固定回應內容")
    request = LLMRequest(system="test", messages=[LLMMessage(role="user", content="hi")])
    response = provider.complete(request)
    assert response.text == "固定回應內容"
    assert response.provider == "mock"


def test_mock_provider_complete_json_parses_valid_json():
    provider = MockProvider('{"key": "value"}')
    request = LLMRequest(system="test", messages=[LLMMessage(role="user", content="hi")])
    response = provider.complete_json(request, schema={"type": "object"})
    assert response.json_data == {"key": "value"}


def test_mock_provider_complete_json_strips_code_fence():
    provider = MockProvider('```json\n{"key": "value"}\n```')
    request = LLMRequest(system="test", messages=[LLMMessage(role="user", content="hi")])
    response = provider.complete_json(request, schema={"type": "object"})
    assert response.json_data == {"key": "value"}


def test_mock_provider_complete_json_raises_on_invalid_json():
    provider = MockProvider("this is not json")
    request = LLMRequest(system="test", messages=[LLMMessage(role="user", content="hi")])
    with pytest.raises(LLMProviderError):
        provider.complete_json(request, schema={"type": "object"})


def test_mock_provider_default_behavior_produces_usable_text():
    # 沒有指定 response_factory 時（seo-advisor write --llm-provider mock 的情境），
    # 應該回傳可用的示範文字，而不是空字串。
    provider = MockProvider()
    request = LLMRequest(
        system="test", messages=[LLMMessage(role="user", content="hi")], response_format="text"
    )
    response = provider.complete(request)
    assert response.text.strip() != ""


def test_mock_provider_default_behavior_produces_valid_brief_json():
    from seo_advisor.writers.pipeline import _BRIEF_SCHEMA
    from seo_advisor.writers.prompts import brief_system_prompt

    provider = MockProvider()
    request = LLMRequest(
        system=brief_system_prompt(),
        messages=[LLMMessage(role="user", content="主題：測試")],
    )
    # complete_json() 會把 schema 序列化塞進 system prompt，MockProvider 依此判斷階段
    response = provider.complete_json(request, _BRIEF_SCHEMA)
    assert response.json_data["primary_intent"] == "informational"
