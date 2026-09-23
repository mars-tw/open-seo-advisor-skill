"""Behavioral and safety coverage for deterministic website output."""

import json
from importlib.resources import files
from io import BytesIO
from xml.etree import ElementTree

import pytest
from bs4 import BeautifulSoup
from PIL import Image
from typer.testing import CliRunner

from seo_advisor.website.builder import build_site, demo_brief
from seo_advisor.website.check import check_site
from seo_advisor.website.cli import website_app
from seo_advisor.website.models import Hero, WebsiteBrief


def encoded_image(format_name):
    output = BytesIO()
    Image.new("RGB", (1, 1), "white").save(output, format=format_name)
    return output.getvalue()


PNG = encoded_image("PNG")
runner = CliRunner()


@pytest.mark.parametrize("kind", ["sales", "shop", "experience"])
@pytest.mark.parametrize("hosting", ["cloudflare", "firebase", "gcp"])
def test_modes_are_readable_offline_and_draft(tmp_path, kind, hosting):
    out = tmp_path / "site"
    report = build_site(demo_brief(kind, hosting), out, base_dir=tmp_path)
    assert report["status"] == "scaffold", report
    assert not report["errors"]
    doc = BeautifulSoup((out / "public/index.html").read_text(encoding="utf-8"), "html.parser")
    for script in doc.find_all("script"):
        script.decompose()
    assert len(doc.select(".chapter h2")) == 3
    assert len(doc.select("details p")) == 3
    assert "山嵐茶屋" in doc.get_text()
    if kind == "shop":
        assert len(doc.select(".product")) == 3
        assert "不收款" in doc.get_text()
        assert all(button.has_attr("hidden") for button in doc.select(".demo-add"))
    elif kind == "experience":
        assert len(doc.select(".mood-notes article")) == 3
    else:
        assert doc.select_one("#selection h2").get_text() == "認識茶席的安排"
        assert doc.select_one("#selection a.button")
    assert doc.find("meta", attrs={"name": "robots"})["content"] == "noindex,follow"
    assert len(ElementTree.parse(out / "public/sitemap.xml").getroot()) == 0
    assert "Disallow: /" not in (out / "public/robots.txt").read_text()
    configs = {"cloudflare": "wrangler.jsonc", "firebase": "firebase.json", "gcp": "Dockerfile"}
    assert (out / configs[hosting]).is_file()
    assert not (out / "public/brief.json").exists()
    manifest = json.loads((out / "asset-manifest.json").read_text(encoding="utf-8"))
    assert manifest["generation_performed"] is False
    assert manifest["assets"][0]["status"] == "pending"


def test_all_text_and_jsonld_are_escaped(tmp_path):
    attack = '</script><img src=x onerror="alert(1)"><script>alert(1)</script>'
    brief = demo_brief()
    brief.brand = attack
    brief.headline = attack
    brief.chapters[0].body = attack
    brief.qa[0].answer = attack
    out = tmp_path / "safe"
    report = build_site(brief, out, base_dir=tmp_path)
    assert not report["errors"]
    doc = BeautifulSoup((out / "public/index.html").read_text(encoding="utf-8"), "html.parser")
    assert not doc.select("[onerror]")
    assert len(doc.find_all("script")) == 3
    structured = json.loads(doc.find("script", attrs={"type": "application/ld+json"}).string)
    assert structured["@graph"][0]["name"] == attack
    assert doc.h1.get_text() == attack


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "http://store.example.com",
        "https://user:pass@example.com",
        "https://example.com\n.evil.test",
        "https://127.0.0.1",
        "//evil.test",
        "https://example.com:8443",
        "https://example.com\\@evil.test",
        "https://test.local",
    ],
)
def test_rejects_unsafe_checkout_urls(url):
    with pytest.raises(ValueError):
        WebsiteBrief(
            brand="Shop",
            site_type="shop",
            products=[{"name": "Tea", "description": "Tea", "checkout_url": url}],
        )


@pytest.mark.parametrize(
    "canonical", ["https://example.com/path", "https://example.com?x=1", "https://example.com/#x"]
)
def test_canonical_is_only_an_origin(canonical):
    with pytest.raises(ValueError):
        WebsiteBrief(brand="Test", canonical=canonical)


def test_never_overwrites_or_accepts_traversal(tmp_path):
    existing = tmp_path / "existing"
    existing.mkdir()
    sentinel = existing / "user.txt"
    sentinel.write_text("keep", encoding="utf-8")
    for target in (existing, tmp_path / "new" / ".." / "escape"):
        with pytest.raises(ValueError):
            build_site(demo_brief(), target, base_dir=tmp_path)
    assert sentinel.read_text() == "keep"
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize("path", ["../outside.png", "/outside.png", "C:\\outside.png"])
def test_rejects_image_path_escape(path):
    with pytest.raises(ValueError):
        WebsiteBrief(brand="Test", assets={"hero": {"path": path, "alt": "image"}})


def test_rejects_fake_raster_and_missing_image_before_writing(tmp_path):
    (tmp_path / "fake.png").write_text("<svg onload='alert(1)'></svg>")
    brief = WebsiteBrief(brand="Test", assets={"hero": {"path": "fake.png", "alt": "image"}})
    with pytest.raises(ValueError):
        build_site(brief, tmp_path / "out", base_dir=tmp_path)
    assert not (tmp_path / "out").exists()


def production_brief(tmp_path, kind="sales"):
    (tmp_path / "hero.png").write_bytes(PNG)
    data = demo_brief(kind).model_dump()
    data.update(
        canonical="https://tea.example.com",
        publication="production",
        content_verified=True,
        title="山嵐茶屋｜預約茶席與茶飲體驗",
        description="山嵐茶屋提供預約制茶席與茶飲體驗。這裡說明服務內容、茶品選擇方式，以及如何預約與取得最新資訊。",
        headline="預約茶席，認識適合自己的茶",
        intro="查看茶席安排、茶飲選擇與預約方式，找到適合自己的體驗。",
        selection_heading="比較茶席與茶飲內容",
        faq_heading="茶席預約與茶飲常見問題",
        contact_heading="查看預約方式",
        experience_intro="依照頁面說明選擇一項內容，閱讀對應的品茶建議。",
        experience_options=(
            [
                {"key": "light-tea", "label": "清香茶", "note": "先閱讀茶品的香氣與沖泡說明。"},
                {"key": "roasted-tea", "label": "焙香茶", "note": "比較焙火程度與適合的飲用情境。"},
            ]
            if kind == "experience"
            else []
        ),
        chapters=[
            {
                "title": "預約茶席的安排",
                "body": "茶席採預約制，訪客可先查看服務內容，再由正式預約管道確認時間。",
            },
            {
                "title": "茶飲如何選擇",
                "body": "茶品依香氣與沖泡方式分類，訪客可比較各品項說明後選擇。",
            },
        ],
        qa=[
            {"question": "如何預約茶席？", "answer": "請使用頁面上的預約連結查看可選時段。"},
            {
                "question": "可以先閱讀茶品資訊嗎？",
                "answer": "可以。商品頁列出品項與用途，購買前可先比較。",
            },
        ],
        pages=[
            {
                "slug": "tea-service",
                "title": "茶席服務安排｜山嵐茶屋",
                "description": "了解山嵐茶屋預約制茶席的內容、適用情境和預約步驟，確認服務是否符合你的需求。",
                "headline": "茶席服務如何安排",
                "intro": "預約前先認識茶席內容與參與方式。",
                "sections": [
                    {
                        "title": "茶席包含什麼",
                        "body": "茶席以沖泡與品飲為主，實際內容依預約頁面的方案資訊為準。",
                    },
                    {
                        "title": "預約前要確認什麼",
                        "body": "請確認可選時段、參與人數與服務條款，再完成預約。",
                    },
                ],
            }
        ],
        assets={"hero": {"path": "hero.png", "alt": "茶席概念示意圖", "source": "gpt-image"}},
        cta={"label": "預約茶席", "url": "https://tea.example.com/book"},
    )
    if kind == "shop":
        for i, product in enumerate(data["products"], 1):
            product["description"] = f"第 {i} 款茶飲，以香氣與沖泡方式供訪客比較選購。"
            product["price_label"] = "NT$ 600"
            product["checkout_url"] = "https://checkout.example.com/tea?sku=1&lang=zh"
    return WebsiteBrief.model_validate(data)


@pytest.mark.parametrize("kind", ["sales", "shop", "experience"])
def test_production_has_image_canonical_and_indexable_sitemap(tmp_path, kind):
    out = tmp_path / "site"
    brief = production_brief(tmp_path, kind)
    report = build_site(brief, out, base_dir=tmp_path)
    assert report["status"] == "baseline_ready", report["errors"]
    assert (out / "public/assets/hero.png").read_bytes() == PNG
    doc = BeautifulSoup((out / "public/index.html").read_text(encoding="utf-8"), "html.parser")
    assert doc.find("link", attrs={"rel": "canonical"})["href"] == "https://tea.example.com/"
    assert doc.find("meta", attrs={"name": "robots"})["content"] == "index,follow"
    assert doc.find("img")["width"] == "1"
    assert doc.find("img")["height"] == "1"
    assert "https://tea.example.com/" in (out / "public/sitemap.xml").read_text()
    assert "https://tea.example.com/tea-service/" in (out / "public/sitemap.xml").read_text()
    assert "Sitemap: https://tea.example.com/sitemap.xml" in (out / "public/robots.txt").read_text()
    detail = BeautifulSoup(
        (out / "public/tea-service/index.html").read_text(encoding="utf-8"), "html.parser"
    )
    assert detail.title.get_text() == "茶席服務安排｜山嵐茶屋"
    assert detail.find("link", attrs={"rel": "canonical"})["href"] == (
        "https://tea.example.com/tea-service/"
    )
    assert [heading.get_text() for heading in detail.select("main h2")][:2] == [
        "茶席包含什麼",
        "預約前要確認什麼",
    ]
    assert doc.select_one('a[href="tea-service/"]')
    if kind == "shop":
        assert not doc.select(".demo-add")
        assert len(doc.select('a[href^="https://checkout.example.com"]')) == 3
    # Saved brief remains portable and supports a clean rebuild with copied assets.
    rebuilt = tmp_path / "rebuilt"
    saved = WebsiteBrief.model_validate_json((out / "brief.json").read_text(encoding="utf-8"))
    assert build_site(saved, rebuilt, base_dir=out)["status"] == "baseline_ready"


def test_incomplete_production_rejected_before_output(tmp_path):
    brief = WebsiteBrief(brand="Test", publication="production")
    with pytest.raises(ValueError, match="production"):
        build_site(brief, tmp_path / "nope", base_dir=tmp_path)
    assert not (tmp_path / "nope").exists()


def test_marking_demo_copy_verified_does_not_publish_placeholders(tmp_path):
    (tmp_path / "hero.png").write_bytes(PNG)
    brief = demo_brief()
    brief.canonical = "https://tea.example.com/"
    brief.publication = "production"
    brief.content_verified = True
    brief.assets.hero = Hero(path="hero.png", alt="茶席")
    brief.cta.url = "https://tea.example.com/book"
    with pytest.raises(ValueError, match="description"):
        build_site(brief, tmp_path / "unsafe-demo", base_dir=tmp_path)
    assert not (tmp_path / "unsafe-demo").exists()


def test_draft_inner_page_links_return_to_home_sections(tmp_path):
    out = tmp_path / "draft"
    brief = demo_brief()
    brief.cta.url = "#selection"
    build_site(brief, out, base_dir=tmp_path)
    page = BeautifulSoup(
        (out / "public/about-the-experience/index.html").read_text(encoding="utf-8"),
        "html.parser",
    )
    assert page.select_one('a.button[href="../#selection"]')
    assert page.select_one('a[href="../#more"]')
    assert page.find("meta", attrs={"name": "robots"})["content"] == "noindex,follow"
    assert check_site(out)["status"] == "scaffold"


def test_hero_is_resized_for_mobile_without_claiming_lcp_result(tmp_path):
    source = tmp_path / "large.png"
    Image.effect_noise((1800, 1200), 30).save(source)
    brief = production_brief(tmp_path)
    brief.assets.hero.path = source.name
    out = tmp_path / "responsive"
    report = build_site(brief, out, base_dir=tmp_path)
    assert report["status"] == "baseline_ready", report["errors"]
    doc = BeautifulSoup((out / "public/index.html").read_text(encoding="utf-8"), "html.parser")
    hero = doc.select_one(".hero-image img")
    assert hero["src"] == "assets/hero.webp"
    assert "assets/hero-mobile.webp" in hero["srcset"]
    assert hero["loading"] == "eager" and hero["fetchpriority"] == "high"
    assert (out / "public/assets/hero.webp").stat().st_size <= 650_000
    assert (out / "public/assets/hero-mobile.webp").stat().st_size <= 220_000
    assert "LCP" in report["scope"] and "live verification" in report["scope"]
    (out / "public/assets/hero-mobile.webp").unlink()
    assert check_site(out)["status"] == "invalid"


@pytest.mark.parametrize("slug", ["../escape", "assets", "Tea Service", "index"])
def test_inner_page_slug_rejects_unsafe_or_reserved_paths(slug):
    page = demo_brief().pages[0].model_dump()
    page["slug"] = slug
    with pytest.raises(ValueError):
        WebsiteBrief(brand="Test", pages=[page])


def test_cli_four_question_init_and_json_exit_status(tmp_path):
    out = tmp_path / "new-site"
    result = runner.invoke(
        website_app, ["init", "--out", str(out)], input="My Brand\nexperience\nfirebase\n\n"
    )
    assert result.exit_code == 0, result.output
    assert json.loads((out / "brief.json").read_text(encoding="utf-8"))["brand"] == "My Brand"
    checked = runner.invoke(website_app, ["check", "--site", str(out)])
    assert checked.exit_code == 2
    assert json.loads(checked.output)["status"] == "scaffold"
    missing = runner.invoke(website_app, ["check", "--site", str(tmp_path / "missing")])
    assert missing.exit_code == 1
    assert json.loads(missing.output)["status"] == "invalid"


def test_check_detects_tampered_public_metadata(tmp_path):
    out = tmp_path / "site"
    build_site(demo_brief(), out, base_dir=tmp_path)
    page = out / "public/index.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace("noindex,follow", "index,follow"), encoding="utf-8"
    )
    report = check_site(out)
    assert report["status"] == "invalid"
    assert not report["checks"]["indexing_intent"]


def test_check_rejects_unrelated_production_home_title(tmp_path):
    brief = production_brief(tmp_path)
    out = tmp_path / "site"
    build_site(brief, out, base_dir=tmp_path)
    page = out / "public/index.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            f"<title>{brief.title}</title>", "<title>與本站無關的活動資訊</title>"
        ),
        encoding="utf-8",
    )
    report = check_site(out)
    assert report["status"] == "invalid"
    assert report["checks"]["title_matches"] is False
    assert report["checks"]["social_metadata"] is False


def test_check_rejects_unrelated_production_home_headings(tmp_path):
    brief = production_brief(tmp_path)
    out = tmp_path / "site"
    build_site(brief, out, base_dir=tmp_path)
    page = out / "public/index.html"
    page.write_text(
        page.read_text(encoding="utf-8").replace(brief.selection_heading, "無關的優惠活動"),
        encoding="utf-8",
    )
    report = check_site(out)
    assert report["status"] == "invalid"
    assert report["checks"]["home_headings_match"] is False


@pytest.mark.parametrize("kind", ["sales", "shop"])
@pytest.mark.parametrize("anchor", ["#main", "#story", "#selection"])
def test_production_sales_or_shop_requires_real_cta(tmp_path, kind, anchor):
    brief = production_brief(tmp_path, kind)
    brief.cta.url = anchor
    with pytest.raises(ValueError, match="HTTPS"):
        build_site(brief, tmp_path / "bad-cta", base_dir=tmp_path)


def test_production_experience_can_link_to_real_onsite_action(tmp_path):
    brief = production_brief(tmp_path, "experience")
    brief.cta.url = "#selection"
    out = tmp_path / "experience"
    report = build_site(brief, out, base_dir=tmp_path)
    assert report["status"] == "baseline_ready", report["errors"]
    doc = BeautifulSoup((out / "public/index.html").read_text(encoding="utf-8"), "html.parser")
    assert [element.get_text() for element in doc.select(".mood-notes h3")] == [
        "清香茶",
        "焙香茶",
    ]


def test_robots_check_distinguishes_private_path_from_full_site_block(tmp_path):
    brief = production_brief(tmp_path)
    out = tmp_path / "site"
    build_site(brief, out, base_dir=tmp_path)
    robots = out / "public/robots.txt"
    original = robots.read_text(encoding="utf-8")
    robots.write_text(original + "Disallow: /private\nDisallow: /cart\n", encoding="utf-8")
    assert check_site(out)["checks"]["robots_crawlable"] is True
    robots.write_text(original + "Disallow: /\n", encoding="utf-8")
    report = check_site(out)
    assert report["status"] == "invalid"
    assert report["checks"]["robots_crawlable"] is False
    robots.write_text(original.replace("Allow: /\n", ""), encoding="utf-8")
    assert check_site(out)["checks"]["robots_crawlable"] is True
    robots.write_text(
        "User-agent: BadBot\nDisallow: /\n\n" + original,
        encoding="utf-8",
    )
    assert check_site(out)["checks"]["robots_crawlable"] is True


def test_resources_and_example_are_available():
    resources = files("seo_advisor.website").joinpath("templates")
    for name in (
        "index.html",
        "styles.css",
        "story.css",
        "site.js",
        "story-timeline.js",
        "brief.example.json",
    ):
        assert resources.joinpath(name).read_text(encoding="utf-8")
    WebsiteBrief.model_validate_json(
        resources.joinpath("brief.example.json").read_text(encoding="utf-8")
    )


def test_non_tea_init_uses_generic_navigation_and_direct_skip(tmp_path):
    out = tmp_path / "generic"
    build_site(WebsiteBrief(brand="精準工業"), out, base_dir=tmp_path)
    doc = BeautifulSoup((out / "public/index.html").read_text(encoding="utf-8"), "html.parser")
    assert "茶席" not in doc.title.get_text()
    assert doc.select_one(".story-skip")["href"] == "#selection"
    assert "--bind 127.0.0.1" in (out / "START-HERE.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("suffix, format_name", [("png", "PNG"), ("jpg", "JPEG"), ("webp", "WEBP")])
def test_actual_raster_decode_required_for_production(tmp_path, suffix, format_name):
    brief = production_brief(tmp_path)
    raster = tmp_path / f"actual.{suffix}"
    raster.write_bytes(encoded_image(format_name))
    brief.assets.hero.path = raster.name
    out = tmp_path / "valid"
    assert build_site(brief, out, base_dir=tmp_path)["status"] == "baseline_ready"
    copied = out / "public/assets" / f"hero.{suffix}"
    copied.write_bytes(copied.read_bytes()[:8])
    checked = check_site(out)
    assert checked["status"] == "invalid"
    assert checked["checks"]["hero_decodable"] is False


@pytest.mark.parametrize(
    "suffix, payload",
    [
        ("png", b"\x89PNG\r\n\x1a\n"),
        ("png", PNG[: len(PNG) // 2]),
        ("jpg", encoded_image("JPEG")[:150]),
        ("webp", encoded_image("WEBP")[:16]),
    ],
)
def test_corrupt_or_truncated_image_rejected_before_writing(tmp_path, suffix, payload):
    brief = production_brief(tmp_path)
    raster = tmp_path / f"broken.{suffix}"
    raster.write_bytes(payload)
    brief.assets.hero.path = raster.name
    out = tmp_path / "rejected"
    with pytest.raises(ValueError, match="圖片"):
        build_site(brief, out, base_dir=tmp_path)
    assert not out.exists()


@pytest.mark.parametrize("host", ["茶屋.台灣", "茶屋.台灣".encode("idna").decode("ascii")])
def test_unicode_and_punycode_domains_roundtrip(host):
    encoded = "茶屋.台灣".encode("idna").decode("ascii")
    brief = WebsiteBrief(
        brand="茶屋", canonical=f"https://{host}", cta={"url": f"https://{host}/booking"}
    )
    assert brief.canonical == f"https://{encoded}/"
    assert brief.cta.url == f"https://{encoded}/booking"


@pytest.mark.parametrize("host", ["test.xn--", "xn--invalid-.com", "test.xn--a", "test.xn--a-"])
def test_malformed_idna_domains_rejected(host):
    with pytest.raises(ValueError):
        WebsiteBrief(brand="Test", canonical=f"https://{host}")


@pytest.mark.parametrize("kind", ["sales", "shop", "experience"])
def test_production_cannot_have_self_loop_contact_cta(tmp_path, kind):
    brief = production_brief(tmp_path, kind)
    brief.cta.url = "#contact"
    with pytest.raises(ValueError, match="行動網址"):
        build_site(brief, tmp_path / "rejected", base_dir=tmp_path)


def test_starter_rejects_language_it_does_not_localize():
    with pytest.raises(ValueError, match="zh-TW"):
        WebsiteBrief(brand="Test", lang="en")
