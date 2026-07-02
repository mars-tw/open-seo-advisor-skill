"""ImageProvider 抽象介面：讓產圖素材專家不綁定單一圖像生成供應商。

設計刻意對照 seo_advisor/writers/providers 的 LLMProvider，讓「provider
抽象層」在整個專案是一致的心智模型。任何新增的圖像供應商（Stability、
本地 SD、未來的模型）都繼承這個介面。

資安要求：API key 只從環境變數讀取，例外訊息不得包含金鑰內容。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from seo_advisor.images.models import ImageArtifact, ImageGenerationRequest


class ImageProviderError(RuntimeError):
    """圖像生成 API 呼叫失敗時拋出（額度用盡、網路錯誤、內容政策拒絕等）。"""


class ImageProvider(ABC):
    @abstractmethod
    def id(self) -> str:
        """回傳 provider 識別字串，例如 'openai'、'mock'。"""

    @abstractmethod
    def capabilities(self) -> set[str]:
        """回傳支援的能力，例如 {'generate'} 或 {'generate', 'edit'}。"""

    @abstractmethod
    def generate_image(
        self, request: ImageGenerationRequest, *, out_dir: str, variant_label: str
    ) -> ImageArtifact:
        """依 request 產生一張圖並寫入 out_dir，回傳 ImageArtifact。

        variant_label 用於區分同一次請求的多個變體（例如 "variant-a"），
        呼叫端（runner）負責迴圈產生 request.variants 張圖。
        """
