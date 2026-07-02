"""MockImageProvider：不需要 API 金鑰，產生佔位 PNG 與 manifest，供 demo/CI/離線試玩。

用最小合法的 PNG（純色方塊）當佔位圖，避免引入 Pillow 之類的相依套件；
真正的圖像品質不是這個 provider 的重點，它的目的是讓整條「需求 → prompt →
生成 → 輸出 manifest」流程在零成本、零金鑰的情況下能完整跑完。
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from seo_advisor.images.models import AspectRatio, ImageArtifact, ImageGenerationRequest
from seo_advisor.images.providers.base import ImageProvider

# 各 aspect ratio 對應的佔位圖尺寸（維持比例，縮小尺寸以加速產生）。
_ASPECT_DIMENSIONS: dict[AspectRatio, tuple[int, int]] = {
    AspectRatio.SQUARE: (256, 256),
    AspectRatio.PORTRAIT_4_5: (256, 320),
    AspectRatio.STORY_9_16: (216, 384),
    AspectRatio.LANDSCAPE_16_9: (384, 216),
    AspectRatio.LANDSCAPE_3_2: (384, 256),
    AspectRatio.PORTRAIT_2_3: (256, 384),
}


def _make_solid_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """手動組出一張純色 PNG，不依賴任何影像處理套件。"""

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + chunk_type
            + data
            + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
        )

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    row = b"\x00" + bytes(rgb) * width
    raw = row * height
    idat = zlib.compress(raw)
    return signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


class MockImageProvider(ImageProvider):
    def id(self) -> str:
        return "mock"

    def capabilities(self) -> set[str]:
        return {"generate"}

    def generate_image(
        self, request: ImageGenerationRequest, *, out_dir: str, variant_label: str
    ) -> ImageArtifact:
        width, height = _ASPECT_DIMENSIONS.get(request.aspect_ratio, (256, 256))
        # 依變體標籤挑不同顏色，讓多變體的佔位圖看得出差異
        palette = [(90, 120, 200), (200, 120, 90), (120, 200, 130), (200, 180, 90)]
        color = palette[hash(variant_label) % len(palette)]

        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        filename = f"{request.use_case.value}-{request.aspect_ratio.value.replace(':', 'x')}-{variant_label}.png"
        file_path = out_path / filename
        file_path.write_bytes(_make_solid_png(width, height, color))

        return ImageArtifact(
            id=f"mock-{variant_label}",
            path=str(file_path),
            provider=self.id(),
            model="mock-image-model",
            prompt=request.prompt,
            width=width,
            height=height,
            aspect_ratio=request.aspect_ratio.value,
            output_format="png",
            use_case=request.use_case.value,
            variant_label=variant_label,
            compliance_notes=["這是 mock provider 產生的佔位圖，並非真實素材。"],
        )
