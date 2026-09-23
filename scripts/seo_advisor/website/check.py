"""Offline baseline checks. A pass is never a production-commerce or ranking claim."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from seo_advisor.website.images import read_raster
from seo_advisor.website.models import WebsiteBrief


def _robots_blocks_root(content: str) -> bool:
    """Only wildcard crawler groups affect the general crawlability baseline."""

    agents: set[str] = set()
    has_rules = False
    group_blocks_root = False
    blocked = False
    for raw_line in content.splitlines():
        if not raw_line.strip():
            blocked = blocked or ("*" in agents and group_blocks_root)
            agents.clear()
            has_rules = False
            group_blocks_root = False
            continue
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            continue
        name, value = (part.strip().casefold() for part in line.split(":", 1))
        if name == "user-agent":
            if has_rules:
                blocked = blocked or ("*" in agents and group_blocks_root)
                agents.clear()
                has_rules = False
                group_blocks_root = False
            agents.add(value)
        elif agents:
            has_rules = True
            if name == "disallow" and value == "/":
                group_blocks_root = True
    return blocked or ("*" in agents and group_blocks_root)


def check_site(site: Path) -> dict:
    errors: list[str] = []
    pending: list[str] = []
    checks: dict[str, bool] = {}
    scope = "offline technical and content baseline only; LCP, accessibility, indexing, AI citations, payments and deployment require separate live verification"

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
        if brief.publication == "production":
            require(
                "title_matches",
                bool(soup.title and soup.title.get_text(strip=True) == brief.title),
                "首頁 title 與已確認的 brief 不一致",
            )
        description = soup.find("meta", attrs={"name": "description"})
        require(
            "description",
            bool(description and description.get("content"))
            and (brief.publication == "draft" or description.get("content") == brief.description),
            "缺少首頁專屬 description，或輸出與 brief 不一致",
        )
        og_title = soup.find("meta", attrs={"property": "og:title"})
        og_description = soup.find("meta", attrs={"property": "og:description"})
        require(
            "social_metadata",
            bool(
                og_title
                and og_title.get("content")
                == (soup.title.get_text(strip=True) if soup.title else "")
                and og_description
                and og_description.get("content")
                == (description.get("content") if description else None)
            ),
            "Open Graph title／description 與頁面 metadata 不一致",
        )
        require(
            "main_heading",
            len(soup.find_all("h1")) == 1 and bool(soup.find("main")),
            "需要單一 h1 與 main",
        )
        if brief.publication == "production":
            home_h1 = soup.select_one("main h1")
            expected_headline = " ".join(brief.headline.split())
            require(
                "home_headings_match",
                bool(home_h1)
                and " ".join(home_h1.get_text(" ", strip=True).split()) == expected_headline
                and bool(
                    soup.select_one("#selection h2")
                    and soup.select_one("#selection h2").get_text(strip=True)
                    == brief.selection_heading
                )
                and bool(
                    soup.select_one("#faq h2")
                    and soup.select_one("#faq h2").get_text(strip=True) == brief.faq_heading
                )
                and bool(
                    soup.select_one("#contact h2")
                    and soup.select_one("#contact h2").get_text(strip=True) == brief.contact_heading
                ),
                "首頁 h1／h2 與已確認的 brief 不一致",
            )
        require(
            "crawlable_story",
            len(soup.select(".chapter h2")) >= 2 and len(soup.select(".chapter p")) >= 2,
            "故事內容必須存在於 HTML",
        )
        if brief.chapters:
            require(
                "story_heading_order",
                [tag.get_text(strip=True) for tag in soup.select(".chapter h2")]
                == [chapter.title for chapter in brief.chapters],
                "故事 h2 與 brief 的主題及順序不一致",
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
        expected_locs = (
            [brief.canonical, *(f"{brief.canonical}{page.slug}/" for page in brief.pages)]
            if brief.publication == "production"
            else []
        )
        require("sitemap", locs == expected_locs, "sitemap 與已發布頁面不一致")
        robots_text = (public / "robots.txt").read_text(encoding="utf-8")
        # Crawlers must be allowed to retrieve a draft and see its noindex.
        require(
            "robots_crawlable",
            not _robots_blocks_root(robots_text),
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

        def check_resources(document: Path, document_soup: BeautifulSoup) -> None:
            ids = {tag["id"] for tag in document_soup.find_all(id=True)}
            for tag in document_soup.find_all(["a", "link", "script", "img"]):
                value = tag.get("href") or tag.get("src")
                if not value:
                    continue
                if value.startswith("#"):
                    if value[1:] not in ids:
                        errors.append(f"找不到頁內連結目標：{document.name} {value}")
                    continue
                parsed = urlsplit(value)
                if parsed.scheme:
                    if parsed.scheme != "https":
                        errors.append("頁面含不安全的資源網址")
                    continue
                if parsed.netloc:
                    errors.append("頁面含未驗證的跨網域資源")
                    continue
                resource = (
                    public / parsed.path.lstrip("/")
                    if parsed.path.startswith("/")
                    else document.parent / parsed.path
                ).resolve()
                if resource.is_dir():
                    resource /= "index.html"
                if not resource.is_relative_to(public.resolve()) or not resource.is_file():
                    errors.append(f"資源不存在或超出 public：{document.name} {value}")

        check_resources(public / "index.html", soup)
        titles = [soup.title.get_text(strip=True)] if soup.title else []
        descriptions = [description.get("content", "")] if description else []
        for page in brief.pages:
            path = public / page.slug / "index.html"
            page_soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
            page_title = page_soup.title.get_text(strip=True) if page_soup.title else ""
            page_description = page_soup.find("meta", attrs={"name": "description"})
            page_description_text = page_description.get("content", "") if page_description else ""
            page_og_title = page_soup.find("meta", attrs={"property": "og:title"})
            page_og_description = page_soup.find("meta", attrs={"property": "og:description"})
            page_canonical = page_soup.find("link", attrs={"rel": "canonical"})
            page_robots = page_soup.find("meta", attrs={"name": "robots"})
            page_h1 = page_soup.select("main h1")
            page_h2 = [tag.get_text(strip=True) for tag in page_soup.select("main h2")]
            require(
                f"page_{page.slug}_metadata",
                page_title == page.title
                and page_description_text == page.description
                and bool(page_og_title and page_og_title.get("content") == page.title)
                and bool(
                    page_og_description and page_og_description.get("content") == page.description
                )
                and (page_canonical.get("href") if page_canonical else None)
                == (f"{brief.canonical}{page.slug}/" if brief.canonical else None)
                and bool(page_robots and page_robots.get("content") == expected),
                f"{page.slug} 的 title、description、canonical 或 robots 錯誤",
            )
            require(
                f"page_{page.slug}_headings",
                len(page_h1) == 1
                and page_h1[0].get_text(strip=True) == page.headline
                and page_h2[: len(page.sections)] == [section.title for section in page.sections],
                f"{page.slug} 的 h1／h2 架構與內容不一致",
            )
            require(
                f"page_{page.slug}_linked",
                bool(soup.select_one(f'a[href="{page.slug}/"]')),
                f"首頁沒有連到 {page.slug} 內頁",
            )
            check_resources(path, page_soup)
            titles.append(page_title)
            descriptions.append(page_description_text)
        require(
            "unique_page_metadata",
            len(titles) == len(set(title.casefold() for title in titles))
            and len(descriptions) == len(set(value.casefold() for value in descriptions)),
            "內頁 title 或 description 重複",
        )
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
                    hero = soup.select_one(".hero-image img")
                    require(
                        "hero_loading_baseline",
                        bool(hero)
                        and hero.get("loading") == "eager"
                        and hero.get("fetchpriority") == "high"
                        and hero.get("width", "").isdigit()
                        and hero.get("height", "").isdigit()
                        and asset.stat().st_size <= 650_000,
                        "首屏圖片需有尺寸、優先載入，且壓縮後不超過 650 KB；LCP 仍須實測",
                    )
                    if hero and hero.get("srcset"):
                        mobile = public / "assets/hero-mobile.webp"
                        mobile_valid = False
                        if mobile.is_file():
                            try:
                                read_raster(mobile)
                            except ValueError:
                                pass
                            else:
                                mobile_valid = True
                        require(
                            "hero_mobile_baseline",
                            mobile_valid
                            and mobile.stat().st_size <= 220_000
                            and "hero-mobile.webp" in hero["srcset"]
                            and bool(hero.get("sizes")),
                            "手機主視覺變體缺失、過大或未設定 responsive sizes；LCP 仍須實測",
                        )
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
                    require(
                        f"{identifier}_budget",
                        asset.stat().st_size
                        <= (150_000 if identifier == "story_actor" else 500_000),
                        f"{identifier} 圖片過大；需先壓縮，實際捲動與 LCP 仍須瀏覽器量測",
                    )
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
