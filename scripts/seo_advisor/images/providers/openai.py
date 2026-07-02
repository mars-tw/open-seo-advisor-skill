"""OpenAIImageProvider：呼叫 OpenAI Images API（gpt-image-1）產生圖像素材。

需要環境變數 OPENAI_API_KEY，以及選配相依套件 `openai`
（`pip install "open-seo-advisor[image-openai]"` 或直接 `pip install openai`）。

GPT image models 預設回傳 base64 編碼的圖像，需 decode 後寫檔。OpenAI 原生
支援的尺寸有限（1024x1024 / 1024x1536 / 1536x1024），因此把專案定義的
aspect ratio 映射到最接近的原生尺寸；4:5、9:16、16:9 等版位若需要精確尺寸，
manifest 會標註「需裁切」，實際裁切留待後續版本（避免強制引入 Pillow 相依）。
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from seo_advisor.images.models import AspectRatio, ImageArtifact, ImageGenerationRequest
from seo_advisor.images.providers.base import ImageProvider, ImageProviderError

_DEFAULT_MODEL = "gpt-image-1"
_API_KEY_ENV_VAR = "OPENAI_API_KEY"

# 把專案的 aspect ratio 映射到 OpenAI 原生支援的尺寸（取最接近的比例）。
_ASPECT_TO_OPENAI_SIZE: dict[AspectRatio, tuple[str, int, int]] = {
    AspectRatio.SQUARE: ("1024x1024", 1024, 1024),
    AspectRatio.PORTRAIT_4_5: ("1024x1536", 1024, 1536),
    AspectRatio.STORY_9_16: ("1024x1536", 1024, 1536),
    AspectRatio.PORTRAIT_2_3: ("1024x1536", 1024, 1536),
    AspectRatio.LANDSCAPE_16_9: ("1536x1024", 1536, 1024),
    AspectRatio.LANDSCAPE_3_2: ("1536x1024", 1536, 1024),
}

_NATIVE_RATIOS = {AspectRatio.SQUARE, AspectRatio.PORTRAIT_2_3, AspectRatio.LANDSCAPE_3_2}


class OpenAIImageProvider(ImageProvider):
    def __init__(self, *, model: str | None = None) -> None:
        api_key = os.environ.get(_API_KEY_ENV_VAR)
        if not api_key:
            raise ImageProviderError(
                f"找不到環境變數 {_API_KEY_ENV_VAR}，無法使用 OpenAI 圖像生成。"
                f"請先設定：export {_API_KEY_ENV_VAR}=your-api-key"
            )

        try:
            import openai
        except ImportError as exc:
            raise ImageProviderError(
                "尚未安裝 openai 套件，請執行：pip install openai"
            ) from exc

        self._client = openai.OpenAI(api_key=api_key)
        self._default_model = model or _DEFAULT_MODEL

    def id(self) -> str:
        return "openai"

    def capabilities(self) -> set[str]:
        return {"generate"}

    def generate_image(
        self, request: ImageGenerationRequest, *, out_dir: str, variant_label: str
    ) -> ImageArtifact:
        import openai

        model = request.model or self._default_model
        size, width, height = _ASPECT_TO_OPENAI_SIZE.get(
            request.aspect_ratio, ("1024x1024", 1024, 1024)
        )

        try:
            response = self._client.images.generate(
                model=model,
                prompt=request.prompt,
                size=size,
                quality=request.quality,
                n=1,
            )
        except openai.APIError as exc:
            raise ImageProviderError(f"OpenAI 圖像生成失敗：{exc}") from exc

        image_b64 = response.data[0].b64_json
        if not image_b64:
            raise ImageProviderError("OpenAI 回應中沒有圖像資料。")
        image_bytes = base64.b64decode(image_b64)

        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        filename = (
            f"{request.use_case.value}-{request.aspect_ratio.value.replace(':', 'x')}-{variant_label}.png"
        )
        file_path = out_path / filename
        file_path.write_bytes(image_bytes)

        compliance_notes: list[str] = []
        if request.aspect_ratio not in _NATIVE_RATIOS:
            compliance_notes.append(
                f"此版位（{request.aspect_ratio.value}）不是 OpenAI 原生尺寸，"
                f"已用最接近的 {size} 產生，實際使用前可能需裁切成目標比例。"
            )

        revised_prompt = getattr(response.data[0], "revised_prompt", None)
        return ImageArtifact(
            id=f"openai-{variant_label}",
            path=str(file_path),
            provider=self.id(),
            model=model,
            prompt=request.prompt,
            revised_prompt=revised_prompt,
            width=width,
            height=height,
            aspect_ratio=request.aspect_ratio.value,
            output_format="png",
            use_case=request.use_case.value,
            variant_label=variant_label,
            compliance_notes=compliance_notes,
        )
