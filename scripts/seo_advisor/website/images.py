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


def _webp_variant(
    source: Image.Image, dimensions: tuple[int, int], budget: int
) -> tuple[bytes, tuple[int, int]]:
    smallest = b""
    smallest_size = source.size
    for scale in (1.0, 0.85, 0.7):
        image = source.copy()
        image.thumbnail(
            (round(dimensions[0] * scale), round(dimensions[1] * scale)),
            Image.Resampling.LANCZOS,
        )
        for quality in (82, 72, 62, 52, 42, 35):
            output = BytesIO()
            image.save(output, format="WEBP", quality=quality, method=5)
            candidate = output.getvalue()
            if not smallest or len(candidate) < len(smallest):
                smallest, smallest_size = candidate, image.size
            if len(candidate) <= budget:
                return candidate, image.size
    return smallest, smallest_size


def prepare_hero(
    path: Path,
) -> tuple[bytes, tuple[int, int], str, tuple[bytes, tuple[int, int]] | None]:
    """Create desktop/mobile first-screen assets; actual LCP still needs measurement."""

    raw, dimensions = read_raster(path)
    desktop = (raw, dimensions, path.suffix.lower())
    mobile = None
    if len(raw) <= 250_000 and max(dimensions) <= 960:
        return *desktop, mobile

    with Image.open(BytesIO(raw)) as source:
        transparent = source.mode in {"RGBA", "LA"} or "transparency" in source.info
        image = source.convert("RGBA" if transparent else "RGB")
        if len(raw) > 650_000 or max(dimensions) > 1800:
            desktop_bytes, desktop_size = _webp_variant(image, (1800, 1800), 650_000)
            desktop = (desktop_bytes, desktop_size, ".webp")
        mobile_bytes, mobile_size = _webp_variant(image, (960, 1280), 220_000)
        if len(mobile_bytes) < len(desktop[0]) and mobile_size[0] < desktop[1][0]:
            mobile = mobile_bytes, mobile_size
    return *desktop, mobile


def prepare_story_asset(path: Path, *, actor: bool = False) -> tuple[bytes, tuple[int, int], str]:
    """Bound the images used by the scroll story before copying them to public."""

    raw, dimensions = read_raster(path)
    budget = 150_000 if actor else 500_000
    edge = 900 if actor else 1600
    if len(raw) <= budget and max(dimensions) <= edge:
        return raw, dimensions, path.suffix.lower()
    with Image.open(BytesIO(raw)) as source:
        transparent = source.mode in {"RGBA", "LA"} or "transparency" in source.info
        image = source.convert("RGBA" if transparent else "RGB")
        optimized, size = _webp_variant(image, (edge, edge), budget)
    return optimized, size, ".webp"
