import json
import struct

import pytest

from seo_advisor.images.compliance import check_image_prompt, contains_sensitive_targeting
from seo_advisor.images.models import AspectRatio, ImageGenerationRequest, ImageUseCase
from seo_advisor.images.providers.factory import create_image_provider
from seo_advisor.images.providers.base import ImageProviderError
from seo_advisor.images.runner import ImageComplianceError, run_image_generation


def _png_is_valid(path):
    data = open(path, "rb").read()
    # PNG signature
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return False
    # IHDR width/height
    width, height = struct.unpack(">II", data[16:24])
    return width > 0 and height > 0


def test_compliance_allows_clean_prompt():
    result = check_image_prompt("一張清爽專業的 SEO 工具介紹圖")
    assert result.allowed is True
    assert result.violations == []


def test_compliance_blocks_competitor_logo():
    result = check_image_prompt("用競品 logo 做一張圖")
    assert result.allowed is False


def test_compliance_blocks_profit_guarantee():
    result = check_image_prompt("保證賺錢的投資廣告圖")
    assert result.allowed is False


def test_sensitive_targeting_detection():
    assert contains_sensitive_targeting("你是不是有憂鬱症") is True
    assert contains_sensitive_targeting("一張產品介紹圖") is False


def test_create_mock_image_provider():
    provider = create_image_provider("mock")
    assert provider.id() == "mock"


def test_create_unknown_image_provider_raises():
    with pytest.raises(ImageProviderError):
        create_image_provider("not-a-real-provider")


def test_openai_image_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ImageProviderError):
        create_image_provider("openai")


def test_run_image_generation_produces_valid_pngs(tmp_path):
    provider = create_image_provider("mock")
    request = ImageGenerationRequest(
        prompt="示範圖", use_case=ImageUseCase.SOCIAL, aspect_ratio=AspectRatio.SQUARE, variants=2
    )
    result = run_image_generation(provider, request, out_dir=str(tmp_path))

    assert len(result.artifacts) == 2
    for artifact in result.artifacts:
        assert _png_is_valid(artifact.path)


def test_run_image_generation_writes_manifest(tmp_path):
    provider = create_image_provider("mock")
    request = ImageGenerationRequest(prompt="示範圖", variants=1)
    run_image_generation(provider, request, out_dir=str(tmp_path))

    manifest = json.loads((tmp_path / "image-manifest.json").read_text(encoding="utf-8"))
    assert manifest["provider"] == "mock"
    assert len(manifest["artifacts"]) == 1


def test_run_image_generation_blocks_forbidden_prompt(tmp_path):
    provider = create_image_provider("mock")
    request = ImageGenerationRequest(prompt="用名人肖像保證賺錢")
    with pytest.raises(ImageComplianceError):
        run_image_generation(provider, request, out_dir=str(tmp_path))


def test_meta_ad_use_case_flags_human_review(tmp_path):
    provider = create_image_provider("mock")
    request = ImageGenerationRequest(
        prompt="產品介紹廣告圖", use_case=ImageUseCase.META_AD, variants=1
    )
    result = run_image_generation(provider, request, out_dir=str(tmp_path))
    assert result.human_review_required is True


def test_aspect_ratio_reflected_in_dimensions(tmp_path):
    provider = create_image_provider("mock")
    request = ImageGenerationRequest(
        prompt="直式故事圖", aspect_ratio=AspectRatio.STORY_9_16, variants=1
    )
    result = run_image_generation(provider, request, out_dir=str(tmp_path))
    artifact = result.artifacts[0]
    assert artifact.height > artifact.width  # 9:16 應該是直式
