"""Plugin Dev Mode 的資料模型：WordPress 外掛 scaffold 產生請求的驗證。

MVP 只支援 `schema-generator` 一個 feature（Organization/WebSite/Article
JSON-LD 產生器），`indexnow-notifier`/`internal-linking` 留待後續版本
（見 docs/roadmap.md）。

slug 是產生的 PHP 檔名、PHP class 名稱前綴、text domain 的共同來源，
必須嚴格驗證格式——這些值最終會被組進 PHP 原始碼（class 名稱、常數
名稱）與檔案系統路徑，格式不嚴謹的話可能產生語法錯誤的 PHP 或不安全的
檔案路徑。
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
_MIN_SLUG_LENGTH = 3
_MAX_SLUG_LENGTH = 64
_MAX_METADATA_LENGTH = 200

# plugin_name/description/author/version/license 這幾個欄位最終會被插入
# PHP 檔案的 docblock 註解（`/** ... */`）與 readme.txt。docblock 沒有
# 跳脫符號的概念（純文字註解），因此不能靠轉義來防注入，只能拒絕含有
# 會提前結束註解區塊（`*/`）、開啟或關閉 PHP tag（`<?php`/`<?=`/`?>`）、
# 或換行符號（會讓內容跨到 docblock 之外，甚至讓後續內容被解讀成程式碼）
# 的輸入。`?>` 目前不是緊迫攻擊面（沒有模板把這些值放進已開啟的 PHP
# context），但作為縱深防禦一併拒絕，避免未來新增模板時不小心踩雷。
_DANGEROUS_METADATA_PATTERN = re.compile(r"\*/|<\?php|<\?=|\?>|\r|\n")


class WordPressPluginFeature(str, Enum):
    SCHEMA_GENERATOR = "schema-generator"


class InvalidPluginRequestError(ValueError):
    """外掛產生請求的參數不合法時拋出。"""


def validate_slug(slug: str) -> str:
    """驗證 WordPress 外掛 slug 格式：全小寫英數字與連字號，開頭必須是
    英文字母，長度 3-64。用來衍生檔名、PHP class 前綴、text domain。
    """
    if not _SLUG_PATTERN.match(slug):
        raise InvalidPluginRequestError(
            f"slug {slug!r} 格式不正確：必須是小寫英數字與連字號組成，"
            "開頭為英文字母，不能連續或開頭/結尾使用連字號。"
        )
    if not (_MIN_SLUG_LENGTH <= len(slug) <= _MAX_SLUG_LENGTH):
        raise InvalidPluginRequestError(
            f"slug {slug!r} 長度必須介於 {_MIN_SLUG_LENGTH}-{_MAX_SLUG_LENGTH} 字元之間。"
        )
    return slug


def validate_metadata_text(value: str, *, field_name: str) -> str:
    """驗證會被插入 PHP docblock 註解的文字欄位（plugin_name/description/
    author/version/license）：拒絕會提前結束註解區塊或注入 PHP tag 的
    內容，並限制長度避免產生的檔案標頭過長。
    """
    if _DANGEROUS_METADATA_PATTERN.search(value):
        raise InvalidPluginRequestError(
            f"{field_name} 不能包含換行符號、'*/' 或 PHP 開始標籤（'<?php'/'<?='），"
            f"這些內容會破壞 PHP 檔案的 docblock 註解結構，收到：{value!r}"
        )
    if len(value) > _MAX_METADATA_LENGTH:
        raise InvalidPluginRequestError(
            f"{field_name} 長度不能超過 {_MAX_METADATA_LENGTH} 字元，目前為 {len(value)} 字元。"
        )
    return value


def slug_to_php_class_prefix(slug: str) -> str:
    """把 slug 轉成 PHP class 名稱慣用的前綴，例如
    "open-seo-schema-helper" -> "Open_SEO_Schema_Helper"。

    只用大寫化每個連字號分隔的片段，不嘗試特殊處理縮寫（例如 SEO 全大寫）
    ——避免針對特定字典做特例判斷，維持轉換規則單純可預期。
    """
    return "_".join(part.capitalize() for part in slug.split("-"))


def slug_to_php_constant_prefix(slug: str) -> str:
    """把 slug 轉成 PHP 常數命名慣用的前綴（全大寫、底線分隔），例如
    "open-seo-schema-helper" -> "OPEN_SEO_SCHEMA_HELPER"。
    """
    return slug.upper().replace("-", "_")


class PluginScaffoldRequest(BaseModel):
    """一次 WordPress 外掛 scaffold 產生請求。"""

    cms: str = Field(default="wordpress")
    feature: WordPressPluginFeature
    plugin_name: str
    slug: str
    description: str = ""
    author: str = "Open SEO Advisor"
    version: str = "0.1.0"
    license: str = "GPL-2.0-or-later"
    zip_output: bool = True

    @field_validator("cms")
    @classmethod
    def _validate_cms(cls, value: str) -> str:
        if value != "wordpress":
            raise InvalidPluginRequestError(f"目前只支援 cms='wordpress'，收到 {value!r}。")
        return value

    @field_validator("slug")
    @classmethod
    def _validate_slug_field(cls, value: str) -> str:
        return validate_slug(value)

    @field_validator("plugin_name")
    @classmethod
    def _validate_plugin_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise InvalidPluginRequestError("plugin_name 不能是空字串。")
        return validate_metadata_text(stripped, field_name="plugin_name")

    @field_validator("description")
    @classmethod
    def _validate_description(cls, value: str) -> str:
        return validate_metadata_text(value, field_name="description")

    @field_validator("author")
    @classmethod
    def _validate_author(cls, value: str) -> str:
        return validate_metadata_text(value, field_name="author")

    @field_validator("version")
    @classmethod
    def _validate_version(cls, value: str) -> str:
        return validate_metadata_text(value, field_name="version")

    @field_validator("license")
    @classmethod
    def _validate_license(cls, value: str) -> str:
        return validate_metadata_text(value, field_name="license")

    @property
    def php_class_prefix(self) -> str:
        return slug_to_php_class_prefix(self.slug)

    @property
    def php_constant_prefix(self) -> str:
        return slug_to_php_constant_prefix(self.slug)

    @property
    def text_domain(self) -> str:
        return self.slug


class PluginScaffoldResult(BaseModel):
    """scaffold 產生結果：寫出的檔案清單與（可選的）zip 路徑。"""

    plugin_dir: str
    written_files: list[str] = Field(default_factory=list)
    zip_path: str | None = None


def resolve_output_dir(out_dir: str, slug: str) -> Path:
    """回傳這次 scaffold 應該寫入的目錄（`<out_dir>/<slug>/`）。"""
    return Path(out_dir) / slug
