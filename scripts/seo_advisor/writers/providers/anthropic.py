"""AnthropicProvider：呼叫 Claude API 產出內容。

需要環境變數 ANTHROPIC_API_KEY，以及選配相依套件 `anthropic`
（`pip install "open-seo-advisor[llm-anthropic]"` 或直接 `pip install anthropic`）。
"""

from __future__ import annotations

import os

from seo_advisor.writers.models import LLMRequest, LLMResponse
from seo_advisor.writers.providers.base import LLMProvider, LLMProviderError

_DEFAULT_MODEL = "claude-sonnet-4-5"
_API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"


class AnthropicProvider(LLMProvider):
    def __init__(self, *, model: str = _DEFAULT_MODEL) -> None:
        api_key = os.environ.get(_API_KEY_ENV_VAR)
        if not api_key:
            raise LLMProviderError(
                f"找不到環境變數 {_API_KEY_ENV_VAR}，無法使用 Anthropic Claude API。"
                f"請先設定：export {_API_KEY_ENV_VAR}=your-api-key"
            )

        try:
            import anthropic
        except ImportError as exc:
            raise LLMProviderError(
                "尚未安裝 anthropic 套件，請執行：pip install anthropic"
            ) from exc

        self._client = anthropic.Anthropic(api_key=api_key)
        self._default_model = model

    def id(self) -> str:
        return "anthropic"

    def capabilities(self) -> set[str]:
        return {"text", "json"}

    def complete(self, request: LLMRequest) -> LLMResponse:
        import anthropic

        model = request.model or self._default_model
        try:
            response = self._client.messages.create(
                model=model,
                max_tokens=request.max_tokens or 4000,
                temperature=request.temperature,
                system=request.system,
                messages=[{"role": m.role, "content": m.content} for m in request.messages],
                timeout=request.timeout_seconds,
            )
        except anthropic.APIError as exc:
            raise LLMProviderError(f"Anthropic API 呼叫失敗：{exc}") from exc

        text = "".join(block.text for block in response.content if hasattr(block, "text"))
        usage = {
            "input_tokens": getattr(response.usage, "input_tokens", None),
            "output_tokens": getattr(response.usage, "output_tokens", None),
        }
        return LLMResponse(text=text, model=model, provider=self.id(), usage=usage)
