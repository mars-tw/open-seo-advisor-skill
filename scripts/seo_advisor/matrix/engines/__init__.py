"""矩陣 engine：把角色派工執行成結果。

Phase 1（目前）：所有角色都透過 MockEngine（免金鑰）或 GenericLLMEngine
（有金鑰時）執行。Phase 2 會把 IRIS→Consultant、MAYA/文案類→Content Writer、
JACK→Meta Ads、PIXEL→Image Material 接到對應的專屬引擎（見 docs/roadmap.md）。
"""

from __future__ import annotations

from seo_advisor.matrix.engines.base import Engine
from seo_advisor.matrix.engines.generic_llm_engine import GenericLLMEngine
from seo_advisor.matrix.engines.mock_engine import MockEngine
from seo_advisor.matrix.models import EngineType


def create_engine(engine_type: EngineType, *, provider_name: str = "mock", model: str | None = None) -> Engine:
    """依 EngineType 建立 engine。

    Phase 1：專屬引擎（consultant/content_writer/meta_ads/image_material）
    尚未接上，統一先用 GenericLLMEngine（provider=mock 時等同 MockEngine），
    確保整條矩陣流程可完整運作且免金鑰可試玩。
    """
    if engine_type == EngineType.MOCK:
        return MockEngine()
    return GenericLLMEngine(provider_name=provider_name, model=model)


__all__ = ["Engine", "MockEngine", "GenericLLMEngine", "create_engine"]
