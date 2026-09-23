"""Build smaller public WebP files from the preserved GPT-generated PNGs."""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent
SOURCES = ROOT / "assets"
ASSETS = ROOT / "public" / "assets"


def export(name: str, width: int | None = None) -> None:
    source = SOURCES / f"{name}.png"
    suffix = f"-{width}" if width else ""
    target = ASSETS / f"{name}{suffix}.webp"
    with Image.open(source) as original:
        image = original.convert("RGB")
    if width:
        height = round(image.height * width / image.width)
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    image.save(target, format="WEBP", quality=90, method=6)
    print(f"{target.name}: {source.stat().st_size} → {target.stat().st_size} bytes")


if __name__ == "__main__":
    for name in ("final", "linework", "underpaint", "studio"):
        export(name)
    export("final", 720)
