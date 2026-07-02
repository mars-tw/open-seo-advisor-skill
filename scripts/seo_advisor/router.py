"""模式路由：依使用者輸入決定要啟動哪個模式。

完整判斷邏輯（含自然語言意圖判斷）見 prompts/router.md，該檔案是給 LLM
使用的 system prompt。這個模組提供 CLI 層可直接使用的簡化版：明確指令
對應與基本關鍵字判斷，複雜的自然語言理解交由呼叫此技能的 LLM 處理。
"""

from __future__ import annotations

from seo_advisor.models import Mode

_MODE_ALIASES: dict[str, Mode] = {
    "consultant": Mode.CONSULTANT,
    "audit": Mode.CONSULTANT,
    "engineer": Mode.ENGINEER,
    "fix": Mode.ENGINEER,
    "security": Mode.SECURITY,
    "content_writer": Mode.CONTENT_WRITER,
    "writer": Mode.CONTENT_WRITER,
    "write": Mode.CONTENT_WRITER,
    "plugin_dev": Mode.PLUGIN_DEV,
    "plugin": Mode.PLUGIN_DEV,
    "ads": Mode.META_ADS,
    "meta_ads": Mode.META_ADS,
    "ad_optimizer": Mode.META_ADS,
    "image": Mode.IMAGE_MATERIAL,
    "image_material": Mode.IMAGE_MATERIAL,
    "creative": Mode.IMAGE_MATERIAL,
    "ecommerce": Mode.ECOMMERCE,
    "amazon": Mode.ECOMMERCE,
    "listing": Mode.ECOMMERCE,
}

_IMPLEMENTED_MODES = {
    Mode.CONSULTANT,
    Mode.CONTENT_WRITER,
    Mode.META_ADS,
    Mode.IMAGE_MATERIAL,
    Mode.ECOMMERCE,
}


class UnknownModeError(ValueError):
    pass


class ModeNotImplementedError(NotImplementedError):
    pass


def resolve_mode(raw: str) -> Mode:
    """把使用者輸入的字串（指令或別名）解析成 Mode。"""
    key = raw.strip().lower().replace("-", "_")
    if key not in _MODE_ALIASES:
        valid = ", ".join(sorted(set(_MODE_ALIASES.keys())))
        raise UnknownModeError(f"無法辨識模式：{raw!r}，可用選項：{valid}")
    return _MODE_ALIASES[key]


def ensure_implemented(mode: Mode) -> None:
    if mode not in _IMPLEMENTED_MODES:
        raise ModeNotImplementedError(
            f"模式 {mode.value} 尚未實作執行邏輯（目前完整實作 consultant 與 content_writer），"
            f"目前僅提供 prompt 模板（見 prompts/{mode.value}.md）與規格"
            f"（見 docs/modes.md），詳見 docs/roadmap.md 的版本規劃。"
        )
