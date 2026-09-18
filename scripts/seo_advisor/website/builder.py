"""Deterministic static rendering; only a new directory is ever written."""

from __future__ import annotations

import html
import json
from importlib.resources import files
from pathlib import Path
from string import Template

from seo_advisor.website.images import read_raster
from seo_advisor.website.models import Answer, Chapter, Product, WebsiteBrief
from seo_advisor.website.story import collect_story_assets, render_story

LABELS = {"sales": "服務提案", "shop": "商品選購", "experience": "互動體驗"}


def load_brief(path: Path) -> WebsiteBrief:
    if path.stat().st_size > 256_000:
        raise ValueError("brief 不可超過 256 KB")
    return WebsiteBrief.model_validate_json(path.read_text(encoding="utf-8-sig"))


def demo_brief(site_type: str = "sales", hosting: str = "cloudflare") -> WebsiteBrief:
    headlines = {
        "sales": "把一天，留一點給山。",
        "shop": "日子慢下來，\n茶香才有地方停。",
        "experience": "循著一縷茶香，\n走進山的時間。",
    }
    return WebsiteBrief(
        brand="山嵐茶屋",
        site_type=site_type,
        hosting=hosting,
        title=f"山嵐茶屋｜{LABELS[site_type]}・互動網站示範",
        description="山嵐茶屋的虛構網站示範。沿著山霧、茶葉與茶席，體驗自然滾動的品牌敘事；商品與服務內容皆待正式確認。",
        headline=headlines[site_type],
        intro="留一口呼吸的空間。從山間的光，到杯裡的暖，讓注意力回到眼前這一刻。",
        chapters=[
            Chapter(
                title="山，先說了話。",
                body="雲影越過坡面，光慢慢落在葉緣。這一段用來放品牌的起點：為什麼做這件事，又想把什麼留給來訪的人。",
            ),
            Chapter(
                title="一片葉的分寸。",
                body="把故事拉近，看見手感與選擇。正式內容可在這裡說明材料、製程或服務細節，每一項說法都應有可確認的依據。",
            ),
            Chapter(
                title="最後，回到你。",
                body="故事走到杯前。這一段留給實際的使用情境：你會在什麼時候使用它，它如何進入你的生活。",
            ),
        ],
        qa=[
            Answer(
                question="現在可以購買或預約嗎？",
                answer="這是虛構品牌的互動示範，尚未開放收款或預約。正式網站會提供確認過的商品、服務與交易資訊。",
            ),
            Answer(
                question="可以關閉頁面動畫嗎？",
                answer="可以。使用右上角的動畫按鈕切換；系統設定為減少動態效果時，網站也會自動停用動態效果。",
            ),
            Answer(
                question="圖片與品牌故事是真實資料嗎？",
                answer="目前為設計示意。正式發布前，須換上已核對的品牌內容，並標示生成圖或實景照片的來源。",
            ),
        ],
        products=(
            [
                Product(
                    name="山霧・清香",
                    description="商品文案示意：以清爽的日常茶飲情境，介紹第一款商品。",
                ),
                Product(
                    name="午後・焙香",
                    description="商品文案示意：從香氣、使用方式與適合的時刻，說明另一種選擇。",
                ),
                Product(
                    name="茶席・相伴",
                    description="商品文案示意：用組合或體驗方案，讓訪客比較不同需求。",
                ),
            ]
            if site_type == "shop"
            else []
        ),
    )


def _e(value: str) -> str:
    return html.escape(value, quote=True)


def _json(value: object) -> str:
    # HTML's script parser recognizes </script> even inside a JSON string.
    return (
        json.dumps(value, ensure_ascii=False, indent=2)
        .replace("<", "\\u003c")
        .replace("&", "\\u0026")
    )


def _asset(
    brief: WebsiteBrief, base: Path
) -> tuple[str | None, bytes | None, tuple[int, int] | None]:
    hero = brief.assets.hero
    if not hero:
        return None, None, None
    base = base.resolve()
    path = (base / hero.path).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError("圖片必須是 brief 目錄內現有的檔案")
    raw, dimensions = read_raster(path)
    suffix = path.suffix.lower()
    return "assets/hero" + suffix, raw, dimensions


def _new_output(out: Path) -> Path:
    if ".." in out.parts:
        raise ValueError("輸出路徑不可含 ..")
    absolute = out.absolute()
    for part in (absolute, *absolute.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError("輸出路徑不可經過符號連結或 junction")
    if absolute.exists():
        raise ValueError("輸出目錄已存在；請選新目錄，避免覆蓋檔案")
    return absolute


def _figure(
    brief: WebsiteBrief, src: str | None, dimensions: tuple[int, int] | None, *, main: bool = False
) -> str:
    if src:
        attrs = 'fetchpriority="high" loading="eager"' if main else 'loading="lazy"'
        size = f' width="{dimensions[0]}" height="{dimensions[1]}"' if dimensions else ""
        return f'<img src="{src}" alt="{_e(brief.assets.hero.alt)}"{size} {attrs} decoding="async">'
    return '<div class="visual-draft" role="img" aria-label="待生成的品牌主視覺佔位"><span>山</span><small>DRAFT VISUAL · 主視覺待生成</small></div>'


def _mode_content(brief: WebsiteBrief) -> str:
    if brief.site_type == "shop":
        products = brief.products or demo_brief("shop").products
        cards = []
        for i, product in enumerate(products, 1):
            if product.checkout_url:
                action = f'<a class="button" href="{_e(product.checkout_url)}" rel="noopener noreferrer">前往外部結帳</a>'
            else:
                action = f'<button class="button demo-add" data-product="{_e(product.name)}" type="button" hidden>加入示範清單</button><p class="fineprint">尚未開放購買；清單不會建立訂單。</p>'
            cards.append(
                f'<article class="product reveal"><div class="product-number" aria-hidden="true">0{i}</div><h3>{_e(product.name)}</h3><p>{_e(product.description)}</p><p class="price">{_e(product.price_label)}</p>{action}</article>'
            )
        cart = ""
        if any(not p.checkout_url for p in products):
            cart = '<aside class="demo-cart" id="cart" aria-label="示範購物清單"><h3>你的示範清單</h3><p>只在此頁暫存，不收款、不送單、不保留個人資料。</p><p id="cart-status" role="status" aria-live="polite">清單目前是空的。</p><ul id="cart-items"></ul><button id="clear-cart" class="text-button" type="button" hidden>清空清單</button><noscript><p>清單互動需要 JavaScript；商品介紹及外部結帳連結仍可閱讀。</p></noscript></aside>'
        return f'<section class="selection section-pad" id="selection"><div class="section-heading"><span class="eyebrow">THE COLLECTION</span><h2>選一份，帶進日常。</h2></div><div class="products">{"".join(cards)}</div>{cart}</section>'
    if brief.site_type == "experience":
        return """<section class="experience section-pad" id="selection"><span class="eyebrow">A MOMENT FOR YOU</span><h2>此刻，想把時間留給什麼？</h2><p>選一個字，替這段旅程留下一個註記。這是頁面互動，不是性格測驗。</p><div class="mood-options" aria-label="選擇此刻的心情"><button type="button" data-mood="quiet" aria-pressed="false" hidden>靜</button><button type="button" data-mood="light" aria-pressed="false" hidden>光</button><button type="button" data-mood="warm" aria-pressed="false" hidden>暖</button></div><div class="mood-notes"><article id="quiet"><h3>靜</h3><p>聽一段沒有急著回答的空白。</p></article><article id="light"><h3>光</h3><p>找找今天曾被你忽略的一小片光。</p></article><article id="warm"><h3>暖</h3><p>把手邊的溫度，多留一會兒。</p></article></div><p id="mood-status" class="fineprint" role="status" aria-live="polite">三種感受，都可以慢慢讀。</p></section>"""
    return f"""<section class="invitation section-pad" id="selection"><span class="eyebrow">AN INVITATION</span><h2>留下一段，<br>好好相處的時間。</h2><p>{_e(brief.intro or '在這裡說明服務適合誰、能提供什麼，以及下一步如何開始。')}</p><a class="button" href="{_e(brief.cta.url)}">{_e(brief.cta.label)}</a><div class="service-steps"><p><span>01</span>了解內容與適用情境</p><p><span>02</span>確認方案與服務細節</p><p><span>03</span>透過正式管道聯繫</p></div></section>"""


def _hosting(brief: WebsiteBrief) -> dict[str, str]:
    if brief.hosting == "cloudflare":
        return {
            "wrangler.jsonc": _json(
                {
                    "name": "my-immersive-site",
                    "compatibility_date": "2026-09-01",
                    "assets": {"directory": "./public", "not_found_handling": "404-page"},
                }
            )
        }
    if brief.hosting == "firebase":
        return {
            "firebase.json": _json(
                {
                    "hosting": {
                        "public": "public",
                        "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
                        "headers": [
                            {
                                "source": "**",
                                "headers": [{"key": "X-Content-Type-Options", "value": "nosniff"}],
                            }
                        ],
                    }
                }
            )
        }
    return {
        "Dockerfile": "FROM nginx:stable-alpine\nCOPY public /usr/share/nginx/html\nCOPY nginx.conf /etc/nginx/templates/default.conf.template\nENV PORT=8080\nEXPOSE 8080\n",
        "nginx.conf": "server {\n  listen ${PORT};\n  server_name _;\n  root /usr/share/nginx/html;\n  index index.html;\n  add_header X-Content-Type-Options nosniff;\n  location / { try_files $uri $uri/ =404; }\n}\n",
        ".dockerignore": "*\n!Dockerfile\n!nginx.conf\n!public\n!public/**\n",
    }


def build_site(brief: WebsiteBrief, out: Path, *, base_dir: Path) -> dict:
    brief = WebsiteBrief.model_validate(brief.model_dump())
    out = _new_output(out)
    image_path, image_bytes, image_dimensions = _asset(brief, base_dir)
    story_assets = collect_story_assets(brief, base_dir)
    if image_bytes:
        identical = next((asset for asset in story_assets if asset["raw"] == image_bytes), None)
        if identical:
            image_path = identical["path"]
    pending = brief.pending()
    if brief.publication == "production" and pending:
        raise ValueError("production 尚未就緒：" + "；".join(pending))
    draft = brief.publication == "draft"
    brand = _e(brief.brand)
    title = brief.title or f"{brief.brand}｜{LABELS[brief.site_type]}・網站草稿"
    description = (
        brief.description
        or f"{brief.brand}的{LABELS[brief.site_type]}網站草稿。品牌內容、圖像素材及正式服務資訊尚待確認。"
    )
    chapters = brief.chapters or [
        Chapter(
            title="故事從哪裡開始？",
            body="請在 brief.chapters 填入品牌的起點、服務對象與真實背景。",
        ),
        Chapter(
            title="讓細節被看見。", body="補上可確認的材料、做法或服務流程，讓訪客理解你的選擇。"
        ),
        Chapter(
            title="下一步，交給來訪的人。",
            body="說明訪客看完之後可以採取的行動，並連到已設定好的正式管道。",
        ),
    ]
    qa = brief.qa or [
        Answer(
            question="這個網站目前可以使用嗎？",
            answer="目前是可瀏覽的網站草稿；服務、圖像與聯絡方式尚待確認。",
        ),
        Answer(
            question="要如何關閉動畫？",
            answer="右上角的動畫按鈕可關閉動態效果；系統減少動態效果設定也會自動生效。",
        ),
    ]
    graph = [
        {"@type": "Organization", "name": brief.brand},
        {
            "@type": "WebSite",
            "name": brief.brand,
            "description": description,
            "inLanguage": brief.lang,
        },
    ]
    canonical_tag = ""
    if brief.canonical:
        canonical_tag = f'<link rel="canonical" href="{_e(brief.canonical)}"><meta property="og:url" content="{_e(brief.canonical)}">'
        for entity in graph:
            entity["url"] = brief.canonical
    og_image = (
        f'<meta property="og:image" content="{_e(brief.canonical + image_path)}">'
        if brief.canonical and image_path
        else ""
    )
    story = "".join(
        f'<article class="chapter reveal" id="chapter-{i}"><span class="eyebrow">CHAPTER / {i:02d}</span><h2>{_e(ch.title)}</h2><p>{_e(ch.body)}</p></article>'
        for i, ch in enumerate(chapters, 1)
    )
    answers = "".join(
        f"<details><summary>{_e(a.question)}</summary><p>{_e(a.answer)}</p></details>" for a in qa
    )
    story_section = (
        render_story(brief, story_assets)
        if brief.story_scenes
        else (
            '<section class="story section-pad" id="story" aria-label="品牌故事">'
            '<div class="story-visual"><figure>'
            + _figure(brief, image_path, image_dimensions)
            + '<figcaption><span>STORY IN MOTION</span><span id="chapter-progress" aria-hidden="true">01</span></figcaption></figure><p class="fineprint">沿著自然捲動的節奏，讀完每一段。</p></div>'
            + f'<div class="chapters">{story}</div></section>'
        )
    )
    template = (
        files("seo_advisor.website").joinpath("templates", "index.html").read_text(encoding="utf-8")
    )
    rendered = Template(template).substitute(
        lang=_e(brief.lang),
        title=_e(title),
        description=_e(description),
        canonical=canonical_tag,
        robots="noindex,follow" if draft else "index,follow",
        og_image=og_image,
        structured_data=_json({"@context": "https://schema.org", "@graph": graph}),
        kind=brief.site_type,
        brand=brand,
        label=LABELS[brief.site_type],
        draft_banner=(
            '<div class="draft-banner" role="note">網站草稿／設計示意 · 內容與交易功能尚待確認</div>'
            if draft
            else ""
        ),
        headline=_e(brief.headline or "從一個故事，\n開始一段相遇。").replace("\n", "<br>"),
        intro=_e(brief.intro or "用可核對的品牌內容，讓訪客讀懂你想提供的價值。"),
        hero=_figure(brief, image_path, image_dimensions, main=True),
        story_section=story_section,
        mode_content=_mode_content(brief),
        qa=answers,
        cta_url=_e(brief.cta.url),
        cta_label=_e(brief.cta.label),
        contact_note=(
            "正式聯絡方式、服務條款與交易資訊待品牌確認。"
            if draft
            else "請透過上方正式連結查看最新服務與交易資訊。"
        ),
    )
    data = {
        "public/index.html": rendered,
        "public/styles.css": files("seo_advisor.website")
        .joinpath("templates", "styles.css")
        .read_text(encoding="utf-8"),
        "public/site.js": files("seo_advisor.website")
        .joinpath("templates", "site.js")
        .read_text(encoding="utf-8"),
        "public/story.css": files("seo_advisor.website")
        .joinpath("templates", "story.css")
        .read_text(encoding="utf-8"),
        "public/story-timeline.js": files("seo_advisor.website")
        .joinpath("templates", "story-timeline.js")
        .read_text(encoding="utf-8"),
        "public/robots.txt": "User-agent: *\nAllow: /\n"
        + (
            f"Sitemap: {brief.canonical}sitemap.xml\n"
            if brief.canonical and not draft
            else "# Draft: pages carry noindex; sitemap has no draft entries.\n"
        ),
        "public/sitemap.xml": '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + (f"<url><loc>{_e(brief.canonical)}</loc></url>" if brief.canonical and not draft else "")
        + "</urlset>\n",
        "public/404.html": '<!doctype html><html lang="zh-TW"><meta charset="utf-8"><meta name="robots" content="noindex"><title>找不到頁面</title><h1>找不到這個頁面</h1><p><a href="/">回到首頁</a></p></html>',
    }
    saved = brief.model_dump(mode="json")
    if image_path:
        saved["assets"]["hero"]["path"] = "public/" + image_path
    for i, asset in enumerate(story_assets):
        if asset["id"] == "actor":
            saved["story_actor"]["path"] = "public/" + asset["path"]
        else:
            saved["story_scenes"][i]["image"]["path"] = "public/" + asset["path"]
    data["brief.json"] = _json(saved)
    data["asset-manifest.json"] = _json(
        {
            "schema_version": 1,
            "generation_performed": False,
            "assets": [
                {
                    "id": "hero",
                    "status": "provided" if image_path else "pending",
                    "source": brief.assets.hero.source if image_path else "gpt-image",
                    "path": "public/" + image_path if image_path else None,
                    "alt": brief.assets.hero.alt if image_path else "待素材生成後描述實際畫面",
                    "prompt": f"Create an original editorial website hero for the brand {brief.brand}. The website purpose is {brief.site_type}. Atmospheric landscape or product still life informed by the approved brand brief. Cinematic natural light, generous negative space for live HTML text, wide 3:2 composition. No text, logos, watermarks, fake certifications or copied reference composition. Do not imply real locations or product details without supplied evidence.",
                    "required_variants": ["desktop 3:2", "mobile 4:5 crop after review"],
                    "review": "生成後確認構圖、品牌事實、來源與授權，匯入 brief.assets.hero。",
                }
            ]
            + [
                {
                    "id": asset["id"],
                    "status": "provided",
                    "source": asset["spec"].source,
                    "path": "public/" + asset["path"],
                    "alt": asset["spec"].alt,
                    "dimensions": list(asset["size"]),
                    "review": "已檢查本地圖片可解碼；構圖、敘事與來源仍需視覺審核。",
                }
                for asset in story_assets
            ],
        }
    )
    data.update(_hosting(brief))
    data["START-HERE.md"] = (
        f"# {brief.brand} 網站專案\n\n"
        "目前是離線產出的可預覽網站；未部署、未生圖、未呼叫 API。\n\n"
        "1. 在本目錄執行 `python -m http.server 8000 --bind 127.0.0.1 --directory public`，開啟 http://localhost:8000。只公開 public，不要公開專案根目錄。\n"
        "2. 將 brief.json 交給網站技能繼續引導。填入真實內容，依 asset-manifest.json 透過 GPT Image 生成並審核圖片。\n"
        "3. 以 `seo-advisor website build --brief brief.json --out ./next-version` 重建到新目錄；不會覆蓋原目錄。\n"
        "4. 執行 `seo-advisor website check --site .`。exit 2 表示草稿待補；exit 0 只表示離線 SEO 基線通過，仍須人工／瀏覽器驗證、交易測試及部署後檢查。\n\n"
        f"選擇的主機：{brief.hosting}。部署前先查核當時免費額度、帳務需求、網域與費用；主機免費不等於生圖、金流、網域全都免費。\n"
        + {
            "cloudflare": "設定 wrangler.jsonc 的唯一專案名稱。Cloudflare 橘雲是 DNS 代理；此設定使用 Workers Static Assets 託管 public。確認帳號與目標後再部署。\n",
            "firebase": "firebase.json 使用 Firebase Hosting，先選擇 Firebase 專案與方案。靜態網站不需要開啟其他 GCP 服務。\n",
            "gcp": "Dockerfile 使用 Cloud Run 相容的 PORT。若選 GCP Cloud Run，先建立自己的專案、確認 Billing 與部署區域，再依 Cloud Run 官方流程建置及部署容器；設 min instances 0、限制 max instances，預算通知不是費用上限。Cloud Run free tier 不代表永遠零費用。\n",
        }[brief.hosting]
        + "\n以下只提供指令，建站工具沒有執行。先完成內容、圖片、網址與交易檢查，再確認目標帳號和發布意願。必須先安裝 Node.js LTS（Cloudflare/Firebase）或 Google Cloud CLI（GCP）。將所有 YOUR_* 代換成自己的設定。\n\n"
        + {
            "cloudflare": "```sh\nnpx wrangler login\nnpx wrangler whoami\nnpx wrangler deploy --dry-run\n# 確認 wrangler.jsonc 專案名稱、帳號及費用後才執行：\nnpx wrangler deploy\n```\n[Cloudflare 官方靜態網站流程](https://developers.cloudflare.com/workers/static-assets/get-started/)\n",
            "firebase": "先在 Firebase Console 建立自己的專案並啟用 Hosting；此專案已備妥 firebase.json，不需要再用 init 覆蓋 public。\n```sh\nnpx firebase-tools login\nnpx firebase-tools projects:list\n# 確認專案與公開內容後才執行：\nnpx firebase-tools deploy --only hosting --project YOUR_PROJECT_ID\n```\n[Firebase 官方部署流程](https://firebase.google.com/docs/hosting/quickstart)\n",
            "gcp": "先建立已連結 Billing 的 GCP 專案，依官方流程確認 Cloud Run、Cloud Build、Artifact Registry 的 API、IAM 與費用。source build 會使用 Cloud Build 與 Artifact Registry，可能另計費。以下會建立公開服務：\n```sh\ngcloud auth login\ngcloud projects describe YOUR_PROJECT_ID\n# 確認 IAM、帳務、區域與公開範圍後才執行：\ngcloud run deploy YOUR_SERVICE_NAME --project YOUR_PROJECT_ID --source . --region YOUR_REGION --allow-unauthenticated --min-instances 0 --max-instances 1\n```\n[Cloud Run 官方 source 部署流程](https://docs.cloud.google.com/run/docs/deploying-source-code)\n",
        }[brief.hosting]
        + "\n購物清單若顯示『示範』，只在瀏覽器記憶體暫存；沒有庫存、訂單、付款或後台。外部結帳是逐項商品連結，不會把示範清單轉成正式訂單。\n"
    )
    out.mkdir(parents=True, exist_ok=False)
    for relative, content in data.items():
        target = out / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    if image_path and not any(asset["path"] == image_path for asset in story_assets):
        target = out / "public" / image_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(image_bytes)
    for asset in story_assets:
        target = out / "public" / asset["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(asset["raw"])
    from seo_advisor.website.check import check_site

    report = check_site(out)
    (out / "site-report.json").write_text(_json(report), encoding="utf-8")
    return {"output": str(out), "preview_directory": str(out / "public"), **report}
