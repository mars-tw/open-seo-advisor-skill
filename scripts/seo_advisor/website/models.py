"""Strict, portable website brief. No credentials, network calls or executable input."""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def safe_url(value: str, *, origin: bool = False, anchor: bool = False) -> str:
    """Validate syntax only: no DNS resolution, private-network request or remote fetch."""
    if anchor and re.fullmatch(r"#[a-z][a-z0-9-]*", value):
        return value
    if any(ord(c) < 33 or c in "\\<>\"'`" for c in value):
        raise ValueError("網址不可含空白、控制字元或 HTML 符號")
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        port = parts.port
    except ValueError as exc:
        raise ValueError("網址格式錯誤") from exc
    if parts.scheme != "https" or parts.username or parts.password or port not in (None, 443):
        raise ValueError("請使用不含帳號密碼的 HTTPS 公開網址")
    try:
        host = host.encode("idna").decode("ascii").lower()
        for label in host.split("."):
            if label.startswith("xn--"):
                label.encode("ascii").decode("idna")
    except UnicodeError as exc:
        raise ValueError("國際化網域格式錯誤") from exc
    if len(host) > 253 or not re.fullmatch(
        r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})", host
    ):
        raise ValueError("網址需使用完整公開網域")
    if host.endswith((".localhost", ".local", ".internal")):
        raise ValueError("不可使用本機或內部網域")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("請使用公開網域而非 IP")
    if origin and (parts.path not in ("", "/") or parts.query or parts.fragment):
        raise ValueError("canonical 請填網站根網址，例如 https://example.com")
    return urlunsplit(("https", host, "/" if origin else parts.path, parts.query, parts.fragment))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def no_control_characters(cls, value):
        if isinstance(value, str) and any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("文字不可含控制字元")
        return value


class Chapter(StrictModel):
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=1600)


class ContentPage(StrictModel):
    """One crawlable page for a distinct topic, separate from the homepage."""

    slug: str = Field(min_length=2, max_length=60, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=350)
    headline: str = Field(min_length=1, max_length=160)
    intro: str = Field(min_length=1, max_length=1600)
    sections: list[Chapter] = Field(min_length=2, max_length=8)

    @field_validator("slug")
    @classmethod
    def reserved_slug(cls, value):
        if value in {"assets", "index", "robots", "sitemap", "404"}:
            raise ValueError("頁面網址使用了系統保留名稱")
        return value


class Answer(StrictModel):
    question: str = Field(min_length=1, max_length=160)
    answer: str = Field(min_length=1, max_length=1600)


class ExperienceOption(StrictModel):
    key: str = Field(min_length=2, max_length=32, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    label: str = Field(min_length=1, max_length=40)
    note: str = Field(min_length=1, max_length=300)


class CTA(StrictModel):
    label: str = Field(default="查看詳細資訊", min_length=1, max_length=60)
    url: str = "#contact"

    @field_validator("url")
    @classmethod
    def validate_url(cls, value):
        return safe_url(value, anchor=True)


class Product(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    price_label: str = Field(default="價格待確認", min_length=1, max_length=60)
    checkout_url: str | None = None

    @field_validator("checkout_url")
    @classmethod
    def validate_checkout(cls, value):
        return safe_url(value) if value else None


class Hero(StrictModel):
    path: str = Field(min_length=1, max_length=400)
    alt: str = Field(min_length=1, max_length=300)
    source: Literal["gpt-image", "provided"] = "provided"

    @field_validator("path")
    @classmethod
    def relative_asset(cls, value):
        path = Path(value)
        if (
            path.anchor
            or value.startswith(("/", "\\"))
            or ".." in value.replace("\\", "/").split("/")
            or ":" in value
        ):
            raise ValueError("素材路徑必須在 brief 目錄內，不能使用絕對路徑或 ..")
        return value


class Assets(StrictModel):
    hero: Hero | None = None


class ScenePoint(StrictModel):
    x: float = Field(default=70, ge=0, le=100, allow_inf_nan=False)
    y: float = Field(default=65, ge=0, le=100, allow_inf_nan=False)


class ActorPose(ScenePoint):
    rotation: float = Field(default=0, ge=-180, le=180, allow_inf_nan=False)
    scale: float = Field(default=1, ge=0.2, le=2, allow_inf_nan=False)


class StoryScene(StrictModel):
    image: Hero
    effect: Literal["mist", "wind", "lanterns", "steam", "none"] = "none"
    actor_pose: ActorPose = Field(default_factory=ActorPose)
    effect_points: list[ScenePoint] = Field(default_factory=list, max_length=8)
    image_position: ScenePoint = Field(default_factory=lambda: ScenePoint(x=70, y=50))


class StoryAction(StrictModel):
    label: str = Field(default="點亮旅程", min_length=1, max_length=60)
    active_label: str = Field(default="光已點亮", min_length=1, max_length=60)
    prompt: str = Field(default="按一下，為這段旅程留一點光。", min_length=1, max_length=160)
    result_text: str = Field(default="你點亮的光，已經抵達。", min_length=1, max_length=300)
    inactive_result_text: str = Field(
        default="旅程已抵達終點。你也可以點亮它，再走一次。", min_length=1, max_length=300
    )


class WebsiteBrief(StrictModel):
    schema_version: Literal[1] = 1
    brand: str = Field(min_length=1, max_length=100)
    site_type: Literal["sales", "shop", "experience"] = "sales"
    hosting: Literal["cloudflare", "firebase", "gcp"] = "cloudflare"
    canonical: str | None = None
    publication: Literal["draft", "production"] = "draft"
    lang: str = "zh-TW"
    title: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=350)
    headline: str = Field(default="", max_length=160)
    intro: str = Field(default="", max_length=1600)
    selection_heading: str = Field(default="", max_length=160)
    faq_heading: str = Field(default="", max_length=160)
    contact_heading: str = Field(default="", max_length=160)
    experience_intro: str = Field(default="", max_length=1600)
    experience_options: list[ExperienceOption] = Field(default_factory=list, max_length=5)
    chapters: list[Chapter] = Field(default_factory=list, max_length=8)
    pages: list[ContentPage] = Field(default_factory=list, max_length=12)
    qa: list[Answer] = Field(default_factory=list, max_length=12)
    cta: CTA = Field(default_factory=CTA)
    products: list[Product] = Field(default_factory=list, max_length=24)
    assets: Assets = Field(default_factory=Assets)
    story_scenes: list[StoryScene] = Field(default_factory=list, max_length=8)
    story_actor: Hero | None = None
    story_start_pose: ActorPose | None = None
    story_action: StoryAction = Field(default_factory=StoryAction)
    content_verified: bool = False

    @model_validator(mode="after")
    def scenes_match_chapters(self):
        if self.story_scenes and (
            len(self.story_scenes) < 2 or len(self.story_scenes) != len(self.chapters)
        ):
            raise ValueError("story_scenes 需至少兩幕，且依序對應每一個 chapters 段落")
        if (self.story_actor or self.story_start_pose) and not self.story_scenes:
            raise ValueError("story_actor／story_start_pose 需搭配 story_scenes")
        if len({page.slug for page in self.pages}) != len(self.pages):
            raise ValueError("pages.slug 不可重複")
        if len({option.key for option in self.experience_options}) != len(self.experience_options):
            raise ValueError("experience_options.key 不可重複")
        for name, values in (
            ("title", [self.title, *(page.title for page in self.pages)]),
            ("description", [self.description, *(page.description for page in self.pages)]),
            ("headline", [self.headline, *(page.headline for page in self.pages)]),
        ):
            filled = [value.strip().casefold() for value in values if value.strip()]
            if len(set(filled)) != len(filled):
                raise ValueError(f"首頁與內頁的 {name} 不可重複")
        return self

    @field_validator("canonical")
    @classmethod
    def validate_canonical(cls, value):
        return safe_url(value, origin=True) if value else None

    @field_validator("lang")
    @classmethod
    def language_tag(cls, value):
        if value != "zh-TW":
            raise ValueError(
                "此離線 starter 目前只支援 zh-TW；其他語言請由建站技能完整在地化後再發布"
            )
        return value

    def pending(self) -> list[str]:
        items = []
        if not self.canonical:
            items.append("canonical 尚未設定")
        for field in ("title", "description", "headline", "intro"):
            if not getattr(self, field):
                items.append(f"{field} 尚未填寫")
        if self.publication == "production":
            for field in ("selection_heading", "faq_heading", "contact_heading"):
                if not getattr(self, field):
                    items.append(f"{field} 尚未填寫")
            if self.site_type in {"sales", "shop"} and self.cta.url.startswith("#"):
                items.append("銷售／購物站需要可用的 HTTPS 聯絡或結帳入口")
            if self.cta.label == "查看詳細資訊":
                items.append("行動按鈕仍是通用文字，請說明訪客會去哪裡")
            if self.site_type == "experience":
                if not self.experience_intro:
                    items.append("experience_intro 尚未填寫")
                if len(self.experience_options) < 2:
                    items.append("互動體驗至少需要兩個已確認的選項")
            draft_terms = (
                "示範",
                "草稿",
                "待確認",
                "請填",
                "虛構",
                "示意",
                "用來放品牌",
                "placeholder",
                "lorem ipsum",
            )
            visible_copy = [
                ("title", self.title),
                ("description", self.description),
                ("headline", self.headline),
                ("intro", self.intro),
                ("selection_heading", self.selection_heading),
                ("faq_heading", self.faq_heading),
                ("contact_heading", self.contact_heading),
                ("experience_intro", self.experience_intro),
                *(
                    (f"chapters.{index}.{field}", getattr(chapter, field))
                    for index, chapter in enumerate(self.chapters, 1)
                    for field in ("title", "body")
                ),
                *(
                    (f"qa.{index}.{field}", getattr(answer, field))
                    for index, answer in enumerate(self.qa, 1)
                    for field in ("question", "answer")
                ),
                *(
                    (f"pages.{page.slug}.{field}", getattr(page, field))
                    for page in self.pages
                    for field in ("title", "description", "headline", "intro")
                ),
                *(
                    (f"pages.{page.slug}.sections.{index}.{field}", getattr(section, field))
                    for page in self.pages
                    for index, section in enumerate(page.sections, 1)
                    for field in ("title", "body")
                ),
                *(
                    (f"products.{index}.{field}", getattr(product, field))
                    for index, product in enumerate(self.products, 1)
                    for field in ("name", "description")
                ),
                *(
                    (f"experience_options.{index}.{field}", getattr(option, field))
                    for index, option in enumerate(self.experience_options, 1)
                    for field in ("label", "note")
                ),
            ]
            for name, value in visible_copy:
                if any(term in value.casefold() for term in draft_terms):
                    items.append(f"{name} 仍含示範或待確認文字")
        if len(self.chapters) < 2:
            items.append("至少需要兩個品牌故事段落")
        if len(self.qa) < 2:
            items.append("至少需要兩組可見問答")
        if not self.assets.hero:
            items.append("GPT 圖像素材尚待生成或匯入")
        if not self.content_verified:
            items.append("品牌事實與文案尚未確認（content_verified）")
        if self.site_type == "shop" and (
            not self.products or any(not p.checkout_url for p in self.products)
        ):
            items.append("購物模式仍含示範購物清單，尚未串接外部結帳")
        if self.site_type == "shop" and any(p.price_label == "價格待確認" for p in self.products):
            items.append("商品價格顯示文字尚未確認")
        if self.cta.url == "#contact":
            items.append("行動網址尚未設定（不可連回按鈕所在的 #contact 區塊）")
        return items
