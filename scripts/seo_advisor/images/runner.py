"""產圖素材專家的執行協調：合規前置檢查 → 逐變體生成 → 輸出 manifest。

CLI 的 image generate/demo/from-content/from-ads 都透過這裡執行，共用同一套
合規檢查與輸出格式。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from seo_advisor.images.compliance import check_image_prompt
from seo_advisor.images.models import ImageArtifact, ImageGenerationRequest, ImageGenerationResult
from seo_advisor.images.providers.base import ImageProvider, ImageProviderError

ProgressCallback = Callable[[str], None]


class ImageComplianceError(ValueError):
    """prompt 未通過合規前置檢查時拋出，不會送出任何圖像生成請求。"""


def _noop(_: str) -> None:
    return None


def _variant_label(index: int) -> str:
    return f"variant-{chr(ord('a') + index)}" if index < 26 else f"variant-{index + 1}"


def run_image_generation(
    provider: ImageProvider,
    request: ImageGenerationRequest,
    *,
    out_dir: str,
    on_progress: ProgressCallback = _noop,
) -> ImageGenerationResult:
    on_progress("合規前置檢查")
    compliance = check_image_prompt(request.prompt, negative_prompt=request.negative_prompt)
    if not compliance.allowed:
        raise ImageComplianceError(
            "圖像需求未通過合規檢查，已拒絕生成（不會送出 API 請求）：\n"
            + "\n".join(f"- {v}" for v in compliance.violations)
        )

    artifacts: list[ImageArtifact] = []
    for i in range(request.variants):
        label = _variant_label(i)
        on_progress(f"產生素材變體 {i + 1}/{request.variants}（{label}）")
        artifact = provider.generate_image(request, out_dir=out_dir, variant_label=label)
        artifacts.append(artifact)

    result = ImageGenerationResult(
        request=request,
        artifacts=artifacts,
        provider=provider.id(),
        model=artifacts[0].model if artifacts else "unknown",
        compliance_notes=compliance.notes,
        human_review_required=request.use_case.value == "meta_ad",
    )

    on_progress("輸出 manifest")
    _write_manifest(result, out_dir)
    return result


def _write_manifest(result: ImageGenerationResult, out_dir: str) -> None:
    manifest_path = Path(out_dir) / "image-manifest.json"
    manifest_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


__all__ = [
    "run_image_generation",
    "ImageComplianceError",
    "ImageProviderError",
]
