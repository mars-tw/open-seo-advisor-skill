"""Offline baseline checks. A pass is never a production-commerce or ranking claim."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from seo_advisor.indexability import google_noindex
from seo_advisor.robots_rules import googlebot_blocked_paths, robots_fields
from seo_advisor.sitemaps import parse_sitemap
from seo_advisor.url_utils import canonical_destination
from seo_advisor.website.images import read_raster
from seo_advisor.website.models import WebsiteBrief
from seo_advisor.website.validation import (
    canonical_targets,
    commercial_claims,
    missing_page_copy,
    images_have_alt,
    jsonld_nodes,
    node_types,
    check_page_resources,
)


def check_site(site: Path) -> dict:
    errors: list[str] = []
    pending: list[str] = []
    checks: dict[str, bool] = {}
    live_checks: set[str] = set()
    responsive_images = []
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
        documents = {public / "index.html": soup}
        origin = brief.canonical or "https://preview.invalid/"
        remote_actions = {
            v
            for v in [brief.cta.url, *(p.checkout_url for p in brief.products)]
            if v and v.startswith("https://")
        }
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
            images_have_alt(soup),
            "圖片缺少替代文字",
        )
        canonical = canonical_targets(soup, origin)
        require(
            "canonical_matches",
            canonical == ({canonical_destination("", brief.canonical)} if brief.canonical else set()),
            f"/ 的 canonical 與 brief 不一致，實際目標：{sorted(canonical)}",
        )
        draft = brief.publication == "draft"
        restrictions = google_noindex(soup)
        require(
            "indexing_intent",
            (
                any(rule.startswith("meta robots:") for rule in restrictions)
                if draft
                else not restrictions
            ),
            "首頁收錄指令與發布狀態不一致：" + (", ".join(restrictions) or "缺少 noindex"),
        )
        sitemap = parse_sitemap((public / "sitemap.xml").read_text(encoding="utf-8"))
        locs = sitemap.urls
        expected_locs = (
            [brief.canonical, *(f"{brief.canonical}{page.slug}/" for page in brief.pages)]
            if brief.publication == "production"
            else []
        )
        require("sitemap", sitemap.kind == "urlset"
                and (not sitemap.problem or (draft and sitemap.count == 0))
                and set(locs) == set(expected_locs), "sitemap 格式或網址與已發布頁面不一致")
        require("sitemap_unique", len(locs) == len(set(locs)), "sitemap 有重複網址")
        robots_text = (public / "robots.txt").read_text(encoding="utf-8")
        # Preview URLs must also be crawlable for Google to see their noindex.
        blocked = googlebot_blocked_paths(
            robots_text, ["/", *(f"/{p.slug}/" for p in brief.pages)]
        )
        require(
            "robots_crawlable",
            not blocked,
            "robots.txt 阻擋 Googlebot 抓取：" + "、".join(blocked),
        )
        if brief.publication == "production":
            require(
                "sitemap_discovery",
                f"{brief.canonical}sitemap.xml" in {v for k, v in robots_fields(robots_text) if k == "sitemap"},
                "robots.txt 缺少 sitemap",
            )

        unverified_claims = []

        def page_nodes(doc, label):
            try:
                nodes = jsonld_nodes(doc)
            except ValueError as exc:
                errors.append(f"{label} JSON-LD 解析失敗：{exc}")
                return []
            claims = commercial_claims(nodes)
            if claims:
                unverified_claims.append(f"{label}（{'、'.join(sorted(claims))}）")
            return nodes

        nodes = page_nodes(soup, "/")
        require(
            "structured_data",
            {"WebSite", "Organization"}.issubset(node_types(nodes)),
            "缺少 WebSite／Organization JSON-LD",
        )
        def check_resources(document: Path, document_soup: BeautifulSoup) -> set[Path]:
            issues, linked_files = check_page_resources(
                document, document_soup, public, origin, remote_actions, live_checks, documents, responsive_images
            )
            errors.extend(issues)
            return linked_files

        home_links = check_resources(public / "index.html", soup)
        titles = [soup.title.get_text(strip=True)] if soup.title else []
        descriptions = [description.get("content", "")] if description else []
        for page in brief.pages:
            path = public / page.slug / "index.html"
            page_soup = documents.get(path)
            if page_soup is None:
                page_soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
                documents[path] = page_soup
            page_title = page_soup.title.get_text(strip=True) if page_soup.title else ""
            page_description = page_soup.find("meta", attrs={"name": "description"})
            page_description_text = page_description.get("content", "") if page_description else ""
            page_og_title = page_soup.find("meta", attrs={"property": "og:title"})
            page_og_description = page_soup.find("meta", attrs={"property": "og:description"})
            expected_canonical = f"{brief.canonical}{page.slug}/" if brief.canonical else None
            canonical = canonical_targets(page_soup, f"{origin}{page.slug}/")
            require(f"page_{page.slug}_canonical", canonical == ({canonical_destination("", expected_canonical)} if expected_canonical else set()),
                    f"/{page.slug}/ 的 canonical 與 brief 不一致，實際目標：{sorted(canonical)}")
            require(f"page_{page.slug}_language", bool(page_soup.html) and
                    page_soup.html.get("lang", "").casefold() == brief.lang.casefold(),
                    f"/{page.slug}/ 的 HTML lang 應為 {brief.lang}")
            missing_copy = missing_page_copy(page_soup, page)
            require(f"page_{page.slug}_copy", not missing_copy,
                    f"/{page.slug}/ 缺少已核定內容：{'、'.join(missing_copy)}")
            page_restrictions = google_noindex(page_soup)
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
                and checks[f"page_{page.slug}_canonical"]
                and (
                    any(rule.startswith("meta robots:") for rule in page_restrictions)
                    if draft
                    else not page_restrictions
                ),
                f"{page.slug} 的 title、description、canonical 或收錄設定錯誤"
                + (f"：{', '.join(page_restrictions)}" if page_restrictions else ""),
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
                path in home_links,
                f"首頁沒有連到 {page.slug} 內頁",
            )
            require(
                f"page_{page.slug}_image_alt",
                images_have_alt(page_soup),
                f"/{page.slug}/ 圖片缺少替代文字",
            )
            detail_nodes = page_nodes(page_soup, f"/{page.slug}/")
            require(
                f"page_{page.slug}_structured_data",
                "WebPage" in node_types(detail_nodes),
                f"/{page.slug}/ 缺少 WebPage JSON-LD",
            )
            check_resources(path, page_soup)
            titles.append(page_title)
            descriptions.append(page_description_text)
        require("no_unverified_ratings", not unverified_claims,
                "頁面的評價或報價缺少可核對的來源與可見內容：" + "、".join(unverified_claims))
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
        "url_validation": "static files and HTML fragments checked offline; deployed HTTP headers, dynamic routes and remote checkout require live verification",
        "links_to_verify_live": sorted(live_checks),
        "responsive_images": responsive_images,
        "checks": checks,
        "errors": errors,
        "pending": pending,
    }
