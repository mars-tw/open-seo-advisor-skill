"""LLMProvider 抽象介面：讓 Content Writer Mode 不綁定單一 LLM 供應商。

任何新增的 provider（例如未來的 Gemini、Mistral）都應該繼承這個介面，
確保 pipeline.py 的呼叫邏輯完全不需要知道底層是哪一家 API，只依賴
LLMRequest -> LLMResponse 這組通用契約。

資安要求：
- API key 一律只能從環境變數讀取，不接受建構子直接傳入明文金鑰參數，
  避免金鑰意外被寫進程式碼、設定檔或指令歷史紀錄。
- 例外訊息不得包含金鑰內容。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from seo_advisor.writers.models import LLMRequest, LLMResponse


class LLMProviderError(RuntimeError):
    """LLM API 呼叫失敗時拋出（額度用盡、網路錯誤、回應格式不符預期等）。"""


class LLMProvider(ABC):
    @abstractmethod
    def id(self) -> str:
        """回傳 provider 識別字串，例如 'anthropic'、'openai'、'local'。"""

    @abstractmethod
    def capabilities(self) -> set[str]:
        """回傳這個 provider 支援的能力，目前固定為 {'text', 'json'} 的子集。"""

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        """執行一次文字生成請求，回傳純文字回應。"""

    def complete_json(self, request: LLMRequest, schema: dict) -> LLMResponse:
        """執行一次要求結構化 JSON 輸出的請求，並驗證回應是否符合 schema。

        預設實作：把 schema 加進 system prompt 提示 LLM 輸出 JSON，呼叫
        complete() 後嘗試解析。子類別如果底層 API 原生支援 JSON mode/
        function calling，應該覆寫這個方法以取得更可靠的結構化輸出。
        """
        import json

        json_request = request.model_copy(
            update={
                "system": (
                    f"{request.system}\n\n"
                    "請只回傳一個符合以下 JSON Schema 的 JSON 物件，"
                    "不要加上任何 markdown code fence 或額外說明文字：\n"
                    f"{json.dumps(schema, ensure_ascii=False)}"
                ),
                "response_format": "json",
            }
        )
        response = self.complete(json_request)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]
        try:
            response.json_data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(
                f"{self.id()} 回傳的內容不是合法 JSON，無法解析：{exc}"
            ) from exc
        return response
