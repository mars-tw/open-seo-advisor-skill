"""Decode local raster assets before accepting them; never fetch remote images."""

import warnings
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError


def read_raster(path: Path) -> tuple[bytes, tuple[int, int]]:
    formats = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP", ".avif": "AVIF"}
    expected = formats.get(path.suffix.lower())
    if not expected:
        raise ValueError("素材只接受 PNG、JPEG、WebP 或 AVIF；不接受 SVG/HTML")
    if path.stat().st_size > 15_000_000:
        raise ValueError("圖片不可超過 15 MB，請先壓縮")
    raw = path.read_bytes()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as image:
                if image.format != expected:
                    raise ValueError("圖片副檔名與實際格式不一致")
                dimensions = image.size
                if (
                    not all(0 < size <= 32768 for size in dimensions)
                    or dimensions[0] * dimensions[1] > 25_000_000
                ):
                    raise ValueError("圖片尺寸超過限制，請縮到 2500 萬像素以下")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError("主視覺只接受單張靜態圖片，請先匯出靜態影格")
                image.verify()
            # verify() checks the container; load() also decodes the pixel data.
            with Image.open(BytesIO(raw)) as image:
                image.load()
    except (
        OSError,
        SyntaxError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("圖片損毀、遭截斷或無法解碼；請重新匯出有效圖片") from exc
    return raw, dimensions
