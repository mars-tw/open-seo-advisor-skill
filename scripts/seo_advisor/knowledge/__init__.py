"""行銷方法論知識庫：中性化蒸餾的通用檢核原則，供各模組共用。

從 methodology.yaml 載入四大領域（ecommerce / paid_ads_funnel / content_brand /
growth_hacking）的檢核原則。用 importlib.resources 讀取，確保打包後可用。

合規說明：知識庫內容為中性化蒸餾（不具名、不含課程名/商標），與
docs/content_writer_guide.md 的合規精神一致。
"""

from __future__ import annotations

import functools
import importlib.resources

import yaml
from pydantic import BaseModel, Field

_ASSET_PACKAGE = "seo_advisor.knowledge"
_METHODOLOGY_FILE = "methodology.yaml"


class MethodologyPrinciple(BaseModel):
    check: str
    why: str


class MethodologyDomain(BaseModel):
    label: str
    principles: list[MethodologyPrinciple] = Field(default_factory=list)
    # 最後一次人工檢視確認這批原則的日期（不代表持續監控更新）。
    # 舊資料若還沒補上這個欄位，預設為 None，不因此讓載入失敗。
    last_reviewed: str | None = None


@functools.lru_cache(maxsize=1)
def load_methodology() -> dict[str, MethodologyDomain]:
    """載入所有領域的方法論原則，回傳 {domain_id: MethodologyDomain}。"""
    traversable = importlib.resources.files(_ASSET_PACKAGE) / _METHODOLOGY_FILE
    with importlib.resources.as_file(traversable) as path:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    domains: dict[str, MethodologyDomain] = {}
    for domain_id, payload in (data.get("domains") or {}).items():
        domains[domain_id] = MethodologyDomain.model_validate(payload)
    return domains


def get_domain(domain_id: str) -> MethodologyDomain | None:
    return load_methodology().get(domain_id)


def list_domains() -> list[str]:
    return list(load_methodology().keys())
