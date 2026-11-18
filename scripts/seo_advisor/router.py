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

_MODE_COMMANDS = {
    Mode.CONSULTANT: "seo-advisor audit consultant --help",
    Mode.CONTENT_WRITER: "seo-advisor write --help",
    Mode.ENGINEER: "seo-advisor fix --help",
    Mode.SECURITY: "seo-advisor security --help",
    Mode.PLUGIN_DEV: "WordPress schema-generator（seo-advisor plugin dev --help）",
    Mode.META_ADS: "seo-advisor ads --help",
    Mode.IMAGE_MATERIAL: "seo-advisor image --help",
    Mode.ECOMMERCE: "seo-advisor ecommerce --help",
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


def mode_command(mode: Mode) -> str:
    try:
        return _MODE_COMMANDS[mode]
    except KeyError as exc:
        raise ModeNotImplementedError(f"模式 {mode.value} 的 CLI 尚未實作。") from exc


def ensure_implemented(mode: Mode) -> None:
    mode_command(mode)
