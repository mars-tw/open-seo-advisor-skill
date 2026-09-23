"""Build smaller public WebP files from the preserved GPT-generated PNGs."""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent
SOURCES = ROOT / "assets"
ASSETS = ROOT / "site" / "public" / "assets"


def export(
    name: str, source_name: str, width: int | None = None, *, lossless: bool = False
) -> None:
    source = SOURCES / source_name
    suffix = f"-{width}" if width else ""
    target = ASSETS / f"{name}{suffix}.webp"
    with Image.open(source) as original:
        image = original.copy()
    if width:
        height = round(image.height * width / image.width)
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    image.save(target, format="WEBP", quality=88, method=6, lossless=lossless)
    print(f"{target.name}: {source.stat().st_size} → {target.stat().st_size} bytes")


if __name__ == "__main__":
    scenes = {
        "scene-01": "scene-01-mist.png",
        "scene-02": "scene-02-bridge.png",
        "scene-03": "scene-03-pavilion.png",
        "scene-04": "scene-04-cup.png",
    }
    for name, source_name in scenes.items():
        export(name, source_name)
    export("scene-01", scenes["scene-01"], 960)
    export("actor", "actor-tea-leaf.png", lossless=True)
