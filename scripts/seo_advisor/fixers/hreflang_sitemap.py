"""sitemap hreflang 產生器：依使用者提供的語言對照表，在 sitemap.xml 的
每個 `<url>` 節點下插入/整組替換 `<xhtml:link rel="alternate" hreflang=
"..." href="...">` 條目。

跟 `fixers/hreflang_generator.py`（HTML `<link>` 標籤）是平行、獨立的
產生器，共用同一份 `hreflang_map.py` 語言對照表；不接進既有
`fixers/sitemap.py`（那裡只處理「sitemap 完全缺失」這個結構清楚的情況，
混入多語 hreflang 邏輯會讓那個模組的職責變複雜）。

修改策略是「in-place 修改既有 `<url>` 節點」，不是重新產生整份 XML：
只在該節點下移除既有的 `xhtml:link rel="alternate"` 子節點、重新附加新的
一組，`<loc>`/`<lastmod>`/`<priority>`/`<changefreq>`/image、video、news
sitemap extension 等其他子節點原樣保留、原始順序不變（NORA 複審指出，
早期版本用「讀 <loc> 重新產生整份 XML」的做法會遺失這些既有 metadata，
是資料遺失風險，已改為這裡的 in-place 策略）。語言對照表裡不存在於既有
sitemap 的 URL 才會新增全新的 `<url>` 節點，append 在檔案最後，不打亂
既有順序（維持小 diff、review 容易）。

只處理標準 `<urlset>` sitemap；如果目標是 sitemap index（`<sitemapindex>`），
降級為 plan_only，提示使用者先指定實際的 URL sitemap 檔案——index 底下
可能有多個子 sitemap，這裡不猜測要修改哪一個。
"""

from __future__ import annotations

from xml.etree import ElementTree

from seo_advisor.fixers.hreflang_map import HreflangMap
from seo_advisor.fixers.models import FixTarget, PatchPlan, ensure_write_target_allowed

_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_XHTML_NS = "http://www.w3.org/1999/xhtml"
_GENERATED_FINDING_ID = "hreflang-sitemap-generator-user-provided-map"
_MAX_URLS_PER_SITEMAP = 50_000

ElementTree.register_namespace("", _SITEMAP_NS)
ElementTree.register_namespace("xhtml", _XHTML_NS)


class SitemapIsIndexError(ValueError):
    """給的是 sitemap index（<sitemapindex>）而非實際 URL sitemap 時拋出。"""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _diff(path: str, before: str, after: str) -> str:
    import difflib

    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def _parse_urlset_root(sitemap_xml: str) -> ElementTree.Element:
    root = ElementTree.fromstring(sitemap_xml)
    if _local_name(root.tag) == "sitemapindex":
        raise SitemapIsIndexError("這是 sitemap index，不是實際的 URL sitemap。")
    if _local_name(root.tag) != "urlset":
        raise ElementTree.ParseError("root 不是 <urlset>。")
    return root


def _new_urlset_root() -> ElementTree.Element:
    return ElementTree.Element(f"{{{_SITEMAP_NS}}}urlset")


def _find_loc_text(url_elem: ElementTree.Element) -> str | None:
    loc_elem = next((c for c in url_elem if _local_name(c.tag) == "loc"), None)
    return loc_elem.text.strip() if loc_elem is not None and loc_elem.text else None


def _replace_hreflang_links(url_elem: ElementTree.Element, alternates: dict[str, str]) -> None:
    """移除該 `<url>` 節點既有的 xhtml:link alternate 子節點，重新附加一組
    新的（依語言代碼字母序，x-default 最後），append 在節點最後——其他
    子節點（loc/lastmod/priority/image 等 extension）位置不受影響。
    """
    for existing in list(url_elem.findall(f"{{{_XHTML_NS}}}link")):
        url_elem.remove(existing)

    non_default = sorted(code for code in alternates if code != "x-default")
    ordered_codes = non_default + (["x-default"] if "x-default" in alternates else [])
    for code in ordered_codes:
        link = ElementTree.SubElement(url_elem, f"{{{_XHTML_NS}}}link")
        link.set("rel", "alternate")
        link.set("hreflang", code)
        link.set("href", alternates[code])


def _serialize(root: ElementTree.Element) -> str:
    ElementTree.indent(root, space="  ")
    body = ElementTree.tostring(root, encoding="unicode", xml_declaration=False)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"


def build_hreflang_sitemap_plan(
    hreflang_map: HreflangMap, *, sitemap_path: str, current_sitemap_xml: str | None
) -> PatchPlan:
    """產出更新 sitemap.xml、加入 hreflang alternate 條目的修復計畫。

    current_sitemap_xml：目前 sitemap.xml 的內容；None 代表檔案不存在
    （這種情況下會建立一份只包含語言對照表裡 URL 的全新 sitemap）。
    """
    total_urls = sum(len(c.alternates) for c in hreflang_map.clusters)
    if total_urls > _MAX_URLS_PER_SITEMAP:
        return _plan_only(
            sitemap_path,
            warnings=[
                f"語言對照表涉及的 URL 總數（{total_urls}）超過單一 sitemap 檔案上限"
                f"（{_MAX_URLS_PER_SITEMAP}），請先拆分成多個 sitemap 檔案再分批處理。"
            ],
        )

    if current_sitemap_xml is not None:
        try:
            root = _parse_urlset_root(current_sitemap_xml)
        except SitemapIsIndexError:
            return _plan_only(
                sitemap_path,
                warnings=[
                    f"{sitemap_path!r} 是 sitemap index（<sitemapindex>），不是實際的 URL sitemap，"
                    "請指定要修改的子 sitemap 檔案路徑。"
                ],
            )
        except ElementTree.ParseError as exc:
            return _plan_only(
                sitemap_path,
                warnings=[f"{sitemap_path!r} 不是合法的 XML，無法安全地插入 hreflang 條目：{exc}"],
            )
    else:
        root = _new_urlset_root()

    try:
        ensure_write_target_allowed(sitemap_path)
    except Exception as exc:  # noqa: BLE001
        return _plan_only(sitemap_path, warnings=[str(exc)])

    url_by_loc: dict[str, ElementTree.Element] = {}
    for url_elem in root:
        if _local_name(url_elem.tag) != "url":
            continue
        loc = _find_loc_text(url_elem)
        if loc:
            url_by_loc[loc] = url_elem

    updated_count = 0
    for cluster in hreflang_map.clusters:
        for url in cluster.alternates.values():
            url_elem = url_by_loc.get(url)
            if url_elem is None:
                url_elem = ElementTree.SubElement(root, f"{{{_SITEMAP_NS}}}url")
                loc_elem = ElementTree.SubElement(url_elem, f"{{{_SITEMAP_NS}}}loc")
                loc_elem.text = url
                url_by_loc[url] = url_elem
            _replace_hreflang_links(url_elem, cluster.alternates)
            updated_count += 1

    fixed = _serialize(root)
    original = current_sitemap_xml or ""

    target = FixTarget(
        path=sitemap_path,
        original_content=original,
        fixed_content=fixed,
        diff_preview=_diff(sitemap_path, original, fixed),
    )

    return PatchPlan(
        plan_id=f"hreflang-sitemap-{_GENERATED_FINDING_ID}",
        finding_id=_GENERATED_FINDING_ID,
        fix_type="hreflang_generate_sitemap",
        risk_level="medium",
        targets=[target],
        summary=(
            f"依使用者提供的語言對照表，為 {updated_count} 個 URL 在 {sitemap_path} 加入/更新 "
            "xhtml:link hreflang alternate 條目，既有的其他 sitemap 欄位（lastmod/priority/"
            "changefreq 等）與 URL 順序不受影響"
            + ("（sitemap 原本不存在，將建立新檔案）" if current_sitemap_xml is None else "。")
        ),
        validation_steps=["重新讀取 sitemap.xml 並確認為合法 XML，且每個語言對照表裡的 URL 都有正確的 hreflang 條目"],
        warnings=[],
    )


def _plan_only(sitemap_path: str, *, warnings: list[str]) -> PatchPlan:
    return PatchPlan(
        plan_id=f"hreflang-sitemap-{_GENERATED_FINDING_ID}",
        finding_id=_GENERATED_FINDING_ID,
        fix_type="hreflang_generate_sitemap",
        risk_level="medium",
        targets=[],
        summary=f"{sitemap_path} 無法自動套用 hreflang 條目，已產出建議。",
        validation_steps=[],
        warnings=warnings,
        plan_only=True,
        suggested_actions=[
            "請檢查上方警告訊息，修正後重新執行；或依語言對照表手動在 sitemap.xml "
            "的每個 <url> 節點下插入 <xhtml:link rel=\"alternate\" hreflang=\"...\" href=\"...\"/>。"
        ],
    )
