"""OpenAIProvider：呼叫 GPT API 產出內容。

需要環境變數 OPENAI_API_KEY，以及選配相依套件 `openai`
（`pip install "open-seo-advisor[llm-openai]"` 或直接 `pip install openai`）。
"""

from __future__ import annotations

import os

from seo_advisor.writers.models import LLMRequest, LLMResponse
from seo_advisor.writers.providers.base import LLMProvider, LLMProviderError

_DEFAULT_MODEL = "gpt-5.2"
_API_KEY_ENV_VAR = "OPENAI_API_KEY"


class OpenAIProvider(LLMProvider):
    def __init__(self, *, model: str = _DEFAULT_MODEL) -> None:
        api_key = os.environ.get(_API_KEY_ENV_VAR)
        if not api_key:
            raise LLMProviderError(
                f"找不到環境變數 {_API_KEY_ENV_VAR}，無法使用 OpenAI GPT API。"
                f"請先設定：export {_API_KEY_ENV_VAR}=your-api-key"
            )

        try:
            import openai
        except ImportError as exc:
            raise LLMProviderError(
                "尚未安裝 openai 套件，請執行：pip install openai"
            ) from exc

        self._client = openai.OpenAI(api_key=api_key)
        self._default_model = model

    def id(self) -> str:
        return "openai"

    def capabilities(self) -> set[str]:
        return {"text", "json"}

    def complete(self, request: LLMRequest) -> LLMResponse:
        import openai

        model = request.model or self._default_model
        messages = [{"role": "system", "content": request.system}]
        messages.extend({"role": m.role, "content": m.content} for m in request.messages)

        try:
            response = self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                timeout=request.timeout_seconds,
            )
        except openai.APIError as exc:
            raise LLMProviderError(f"OpenAI API 呼叫失敗：{exc}") from exc

        text = response.choices[0].message.content or ""
        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }
        return LLMResponse(text=text, model=model, provider=self.id(), usage=usage)
