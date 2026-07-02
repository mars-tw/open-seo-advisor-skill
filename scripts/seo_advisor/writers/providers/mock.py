"""MockProvider：測試與離線開發用，回傳固定或可程式化的假回應，不呼叫任何真實 API。

在 CLI 情境下（`seo-advisor write --llm-provider mock`），沒有自訂
response_factory 時會依請求的 response_format 自動產生合理的假資料，
讓使用者不需要任何 API 金鑰就能完整體驗 brief -> outline -> draft -> QA
四個階段的報告長相，跟 Consultant Mode 的 demo 模式扮演類似角色。
"""

from __future__ import annotations

import json
from typing import Callable

from seo_advisor.writers.models import LLMRequest, LLMResponse
from seo_advisor.writers.providers.base import LLMProvider

ResponseFactory = Callable[[LLMRequest], str]

_DEFAULT_JSON_BY_SCHEMA_FIELD: list[tuple[str, dict]] = [
    # 用 complete_json() 塞入 system prompt 的 JSON Schema 欄位名稱判斷目前是
    # 哪個階段的請求（brief/outline/QA），比用 prompt 文字本身的關鍵字比對
    # 更準確，因為 schema 欄位名稱是程式碼層面固定的契約，不受文案調整影響。
    (
        '"primary_intent"',
        {
            "primary_intent": "informational",
            "secondary_intents": [],
            "reader_tasks": ["（示範資料）了解這個主題的基本概念"],
            "must_cover_questions": ["（示範資料）這個主題最常見的問題是什麼"],
            "content_gaps": [],
            "eeat_needs": ["加入實際案例或第一手經驗"],
            "is_ymyl": False,
            "facts_needing_verification": [],
        },
    ),
    (
        '"sections"',
        {
            "sections": [
                {"heading": "（示範資料）主題介紹", "level": 2, "goal": "建立基本認識"},
                {"heading": "（示範資料）常見問題", "level": 2, "goal": "回答讀者疑問"},
            ],
            "title_variants": ["（示範資料）標題選項"],
            "meta_description_variants": ["（示範資料）meta description"],
            "schema_recommendation": "Article",
            "internal_link_plan": [],
        },
    ),
    (
        '"quality_score"',
        {
            "passed": True,
            "quality_score": 75,
            "issues": [],
            "human_review_notes": ["這是 mock provider 產生的示範資料，並非真實審核結果。"],
        },
    ),
]


def _default_response_for(request: LLMRequest) -> str:
    if request.response_format == "json":
        for schema_field, payload in _DEFAULT_JSON_BY_SCHEMA_FIELD:
            if schema_field in request.system:
                return json.dumps(payload, ensure_ascii=False)
        return json.dumps({}, ensure_ascii=False)
    return "# （示範資料）文章草稿\n\n這是 mock provider 產生的示範草稿內容，並非真實文章。"


class MockProvider(LLMProvider):
    def __init__(self, response_factory: ResponseFactory | str | None = None) -> None:
        self._response_factory = response_factory

    def id(self) -> str:
        return "mock"

    def capabilities(self) -> set[str]:
        return {"text", "json"}

    def complete(self, request: LLMRequest) -> LLMResponse:
        if self._response_factory is None:
            text = _default_response_for(request)
        elif callable(self._response_factory):
            text = self._response_factory(request)
        else:
            text = self._response_factory
        return LLMResponse(text=text, model="mock-model", provider=self.id())
