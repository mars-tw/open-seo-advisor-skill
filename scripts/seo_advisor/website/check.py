"""Offline baseline checks. A pass is never a production-commerce or ranking claim."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from seo_advisor.website.images import read_raster
from seo_advisor.website.models import WebsiteBrief


def check_site(site: Path) -> dict:
    errors: list[str] = []
    pending: list[str] = []
    checks: dict[str, bool] = {}
    scope = "offline SEO/AEO baseline only; visual, accessibility, live indexing, payments and deployment require separate verification"

    def require(name: str, condition: bool, message: str) -> None:
        checks[name] = bool(condition)
        if not condition:
            errors.append(message)

    try:
        site = site.resolve()
        public = site / "public"
        brief = WebsiteBrief.model_validate_json((site / "brief.json").read_text(encoding="utf-8"))
        html = (public / "index.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(html, "html.parser")
        pending = brief.pending()
        if brief.publication == "draft":
            pending.insert(0, "publication=draft；預設 noindex，尚未作為正式網站發布")
        require(
            "language", bool(soup.html and soup.html.get("lang") == brief.lang), "缺少正確頁面語言"
        )
        require("title", bool(soup.title and soup.title.get_text(strip=True)), "缺少 title")
        description = soup.find("meta", attrs={"name": "description"})
        require("description", bool(description and description.get("content")), "缺少 description")
        require(
            "main_heading",
            len(soup.find_all("h1")) == 1 and bool(soup.find("main")),
            "需要單一 h1 與 main",
        )
        require(
            "crawlable_story",
            len(soup.select(".chapter h2")) >= 2 and len(soup.select(".chapter p")) >= 2,
            "故事內容必須存在於 HTML",
        )
        require(
            "visible_answers",
            len(soup.select("#faq details summary")) >= 2
            and len(soup.select("#faq details p")) >= 2,
            "缺少可見的完整問答",
        )
        require(
            "image_alt",
            all(image.get("alt", "").strip() for image in soup.find_all("img")),
            "圖片缺少替代文字",
        )
        canonical = soup.find("link", attrs={"rel": "canonical"})
        require(
            "canonical_matches",
            (canonical.get("href") if canonical else None) == brief.canonical,
            "canonical 與 brief 不一致",
        )
        robots = soup.find("meta", attrs={"name": "robots"})
        expected = "noindex,follow" if brief.publication == "draft" else "index,follow"
        require(
            "indexing_intent",
            bool(robots and robots.get("content") == expected),
            "robots meta 與發布狀態不一致",
        )
        sitemap = ElementTree.fromstring((public / "sitemap.xml").read_text(encoding="utf-8"))
        locs = [
            item.text
            for item in sitemap.findall(
                "{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
            )
        ]
        require(
            "sitemap",
            locs == ([brief.canonical] if brief.publication == "production" else []),
            "sitemap 與發布狀態不一致",
        )
        robots_text = (public / "robots.txt").read_text(encoding="utf-8")
        # Crawlers must be allowed to retrieve a draft and see its noindex.
        require(
            "robots_crawlable",
            "User-agent: *" in robots_text
            and "Allow: /" in robots_text
            and "Disallow: /" not in robots_text,
            "robots.txt 不可阻止讀取 noindex",
        )
        if brief.publication == "production":
            require(
                "sitemap_discovery",
                f"Sitemap: {brief.canonical}sitemap.xml" in robots_text,
                "robots.txt 缺少 sitemap",
            )
        nodes = []
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            obj = json.loads(script.get_text())
            nodes.extend(obj.get("@graph", [obj]))
        require(
            "structured_data",
            {"WebSite", "Organization"}.issubset({node.get("@type") for node in nodes}),
            "缺少 WebSite／Organization JSON-LD",
        )
        require(
            "no_unverified_ratings",
            all(
                "aggregateRating" not in node and "review" not in node and "offers" not in node
                for node in nodes
            ),
            "此 starter 不支援未核對的評價、Offer",
        )
        ids = {tag["id"] for tag in soup.find_all(id=True)}
        for tag in soup.find_all(["a", "link", "script", "img"]):
            value = tag.get("href") or tag.get("src")
            if not value:
                continue
            if value.startswith("#"):
                if value[1:] not in ids:
                    errors.append(f"找不到頁內連結目標：{value}")
            elif not urlsplit(value).scheme:
                resource = (public / value).resolve()
                if not resource.is_relative_to(public.resolve()) or not resource.is_file():
                    errors.append(f"資源不存在或超出 public：{value}")
            elif urlsplit(value).scheme != "https":
                errors.append("頁面含不安全的資源網址")
        css = (public / "styles.css").read_text(encoding="utf-8")
        js = (public / "site.js").read_text(encoding="utf-8")
        require(
            "motion_fallback",
            "prefers-reduced-motion" in css
            and 'data-motion="off"' in css
            and bool(soup.select_one("#motion-toggle")),
            "缺少減少動態效果支援",
        )
        require(
            "local_enhancement",
            "preventDefault" not in js and "innerHTML" not in js,
            "互動不可接管自然滾動或直接插入未轉義 HTML",
        )
        if brief.assets.hero:
            asset = (site / brief.assets.hero.path).resolve()
            require(
                "provided_hero",
                asset.is_relative_to(public.resolve()) and asset.is_file(),
                "hero 不在 public 或檔案不存在",
            )
            if checks["provided_hero"]:
                try:
                    read_raster(asset)
                except ValueError as exc:
                    require("hero_decodable", False, str(exc))
                else:
                    require("hero_decodable", True, "")
        if brief.site_type == "shop":
            require("shop_content", bool(soup.select(".product")), "缺少商品內容")
        if brief.story_scenes:
            expected_links = [f"#chapter-{i}" for i in range(1, len(brief.story_scenes) + 1)]
            require(
                "story_navigation",
                [link.get("href") for link in soup.select("[data-chapter-link]")] == expected_links,
                "故事導覽需逐一連到每幕真實錨點",
            )
            require(
                "story_static_fallback",
                len(soup.select(".story-beat .beat-static")) == len(brief.story_scenes),
                "每幕需要無 JavaScript 也可閱讀的圖文",
            )
            require(
                "story_scene_layers",
                len(soup.select(".scene-layer")) == len(brief.story_scenes),
                "故事舞台與分幕數量不一致",
            )
            require(
                "story_controls",
                bool(soup.select_one('.story-tools a[href="#selection"]'))
                and bool(soup.select_one('[data-story-replay][href="#chapter-1"]'))
                and bool(soup.select_one('.story-action[type="button"]')),
                "故事需提供略過、重看及鍵盤可操作按鈕",
            )
            assets = [(f"scene_{i}", scene.image) for i, scene in enumerate(brief.story_scenes, 1)]
            if brief.story_actor:
                assets.append(("story_actor", brief.story_actor))
                require(
                    "story_persistent_actor",
                    bool(soup.select_one(".stage-actor img")),
                    "缺少持續存在的前景角色",
                )
            for identifier, specification in assets:
                asset = (site / specification.path).resolve()
                inside = asset.is_relative_to(public.resolve()) and asset.is_file()
                require(f"{identifier}_file", inside, f"{identifier} 圖片不在 public 或檔案不存在")
                if inside:
                    relative = asset.relative_to(public.resolve()).as_posix()
                    require(
                        f"{identifier}_rendered",
                        bool(soup.find("img", attrs={"src": relative})),
                        f"{identifier} 圖片未出現在 HTML",
                    )
                    try:
                        read_raster(asset)
                    except ValueError as exc:
                        require(f"{identifier}_decodable", False, f"{identifier}：{exc}")
                    else:
                        require(f"{identifier}_decodable", True, "")
        if brief.publication == "production" and pending:
            errors.append("production brief 仍有待補項目")
    except (OSError, ValueError, TypeError, AttributeError, ElementTree.ParseError) as exc:
        errors.append(f"無法驗證專案：{exc}")
    return {
        "status": "invalid" if errors else "scaffold" if pending else "baseline_ready",
        "scope": scope,
        "network_requests": False,
        "url_validation": "syntax only; DNS, reachability and remote checkout are not verified",
        "checks": checks,
        "errors": errors,
        "pending": pending,
    }
