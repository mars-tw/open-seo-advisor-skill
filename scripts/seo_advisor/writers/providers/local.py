"""LocalProvider：呼叫本機或自架的 Ollama 相容 HTTP 端點，不需要任何 API key。

這是唯一一個「完全不依賴付費雲端服務」的 provider，讓沒有 API 預算的使用者
（尤其是開源社群貢獻者）也能完整體驗 Content Writer Mode，只要本機有安裝
Ollama（或其他相容 /api/generate 介面的服務）即可。
"""

from __future__ import annotations

import os

import httpx

from seo_advisor.writers.models import LLMRequest, LLMResponse
from seo_advisor.writers.providers.base import LLMProvider, LLMProviderError

_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_MODEL = "llama3.1"
_BASE_URL_ENV_VAR = "OLLAMA_BASE_URL"


class LocalProvider(LLMProvider):
    def __init__(self, *, model: str = _DEFAULT_MODEL, base_url: str | None = None) -> None:
        self._base_url = base_url or os.environ.get(_BASE_URL_ENV_VAR, _DEFAULT_BASE_URL)
        self._default_model = model

    def id(self) -> str:
        return "local"

    def capabilities(self) -> set[str]:
        return {"text", "json"}

    def complete(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self._default_model
        prompt_parts = [request.system]
        prompt_parts.extend(m.content for m in request.messages)
        prompt = "\n\n".join(prompt_parts)

        try:
            response = httpx.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": request.temperature},
                },
                timeout=request.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMProviderError(
                f"無法連線到本地 LLM 服務（{self._base_url}）：{exc}。"
                "請確認 Ollama（或相容服務）已啟動，或設定 OLLAMA_BASE_URL 環境變數。"
            ) from exc

        data = response.json()
        text = data.get("response", "")
        return LLMResponse(text=text, model=model, provider=self.id())
