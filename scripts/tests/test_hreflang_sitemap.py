from xml.etree import ElementTree

from seo_advisor.fixers.hreflang_map import parse_language_map
from seo_advisor.fixers.hreflang_sitemap import build_hreflang_sitemap_plan

_XHTML_NS = "{http://www.w3.org/1999/xhtml}"
_SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _map() -> object:
    return parse_language_map(
        {
            "clusters": [
                {
                    "id": "home",
                    "alternates": {
                        "zh-TW": "https://example.com/zh/",
                        "en": "https://example.com/en/",
                        "x-default": "https://example.com/",
                    },
                }
            ]
        }
    )


class TestBuildHreflangSitemapPlan:
    def test_creates_sitemap_when_missing(self):
        plan = build_hreflang_sitemap_plan(_map(), sitemap_path="sitemap.xml", current_sitemap_xml=None)
        assert not plan.plan_only
        assert len(plan.targets) == 1
        root = ElementTree.fromstring(plan.targets[0].fixed_content)
        assert root.tag == f"{_SITEMAP_NS}urlset"
        locs = {el.text for el in root.iter(f"{_SITEMAP_NS}loc")}
        assert locs == {"https://example.com/zh/", "https://example.com/en/", "https://example.com/"}

    def test_each_cluster_url_gets_full_alternate_set(self):
        plan = build_hreflang_sitemap_plan(_map(), sitemap_path="sitemap.xml", current_sitemap_xml=None)
        root = ElementTree.fromstring(plan.targets[0].fixed_content)
        for url_elem in root.iter(f"{_SITEMAP_NS}url"):
            alt_hreflangs = {el.get("hreflang") for el in url_elem.iter(f"{_XHTML_NS}link")}
            assert alt_hreflangs == {"zh-TW", "en", "x-default"}

    def test_preserves_unrelated_existing_urls(self):
        existing = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<url><loc>https://example.com/other-page</loc></url>"
            "</urlset>"
        )
        plan = build_hreflang_sitemap_plan(_map(), sitemap_path="sitemap.xml", current_sitemap_xml=existing)
        assert "https://example.com/other-page" in plan.targets[0].fixed_content
        root = ElementTree.fromstring(plan.targets[0].fixed_content)
        locs = {el.text for el in root.iter(f"{_SITEMAP_NS}loc")}
        assert "https://example.com/other-page" in locs
        assert len(locs) == 4

    def test_existing_url_matching_cluster_gets_hreflang_added(self):
        existing = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<url><loc>https://example.com/en/</loc></url>"
            "</urlset>"
        )
        plan = build_hreflang_sitemap_plan(_map(), sitemap_path="sitemap.xml", current_sitemap_xml=existing)
        fixed = plan.targets[0].fixed_content
        assert 'hreflang="zh-TW"' in fixed
        assert 'hreflang="x-default"' in fixed

    def test_sitemap_index_degrades_to_plan_only(self):
        index_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<sitemap><loc>https://example.com/sitemap1.xml</loc></sitemap>"
            "</sitemapindex>"
        )
        plan = build_hreflang_sitemap_plan(_map(), sitemap_path="sitemap.xml", current_sitemap_xml=index_xml)
        assert plan.plan_only
        assert plan.targets == []
        assert any("sitemap index" in w for w in plan.warnings)

    def test_invalid_xml_degrades_to_plan_only(self):
        plan = build_hreflang_sitemap_plan(_map(), sitemap_path="sitemap.xml", current_sitemap_xml="not xml")
        assert plan.plan_only
        assert plan.targets == []

    def test_disallowed_extension_degrades_to_plan_only(self):
        plan = build_hreflang_sitemap_plan(_map(), sitemap_path="sitemap.php", current_sitemap_xml=None)
        assert plan.plan_only
        assert plan.targets == []

    def test_fix_type_is_sitemap_specific(self):
        plan = build_hreflang_sitemap_plan(_map(), sitemap_path="sitemap.xml", current_sitemap_xml=None)
        assert plan.fix_type == "hreflang_generate_sitemap"

    def test_output_is_deterministic_url_order(self):
        plan_a = build_hreflang_sitemap_plan(_map(), sitemap_path="sitemap.xml", current_sitemap_xml=None)
        plan_b = build_hreflang_sitemap_plan(_map(), sitemap_path="sitemap.xml", current_sitemap_xml=None)
        assert plan_a.targets[0].fixed_content == plan_b.targets[0].fixed_content

    def test_preserves_existing_metadata_fields(self):
        """NORA 複審指出：早期版本重新產生整份 XML 只保留 <loc>，會遺失
        既有的 lastmod/priority/changefreq。已改為 in-place 修改，這裡
        鎖住不再回歸。"""
        existing = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<url><loc>https://example.com/en/</loc>"
            "<lastmod>2026-02-02</lastmod><priority>0.9</priority>"
            "<changefreq>weekly</changefreq></url>"
            "</urlset>"
        )
        plan = build_hreflang_sitemap_plan(_map(), sitemap_path="sitemap.xml", current_sitemap_xml=existing)
        fixed = plan.targets[0].fixed_content
        assert "<lastmod>2026-02-02</lastmod>" in fixed
        assert "<priority>0.9</priority>" in fixed
        assert "<changefreq>weekly</changefreq>" in fixed

    def test_preserves_original_url_order_and_appends_new_ones_last(self):
        existing = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<url><loc>https://example.com/zulu-page</loc></url>"
            "<url><loc>https://example.com/en/</loc></url>"
            "</urlset>"
        )
        plan = build_hreflang_sitemap_plan(_map(), sitemap_path="sitemap.xml", current_sitemap_xml=existing)
        fixed = plan.targets[0].fixed_content
        zulu_pos = fixed.index("zulu-page")
        en_pos = fixed.index("<loc>https://example.com/en/</loc>")
        zh_pos = fixed.index("zh/")
        assert zulu_pos < en_pos < zh_pos  # 既有順序不變（zulu 在字母序上該排最後，但這裡驗證原始順序被保留）

    def test_replaces_only_hreflang_link_not_other_children(self):
        existing = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml">'
            "<url><loc>https://example.com/en/</loc>"
            '<xhtml:link rel="alternate" hreflang="fr" href="https://old.example.com/fr/"/>'
            "<lastmod>2026-01-01</lastmod></url>"
            "</urlset>"
        )
        plan = build_hreflang_sitemap_plan(_map(), sitemap_path="sitemap.xml", current_sitemap_xml=existing)
        fixed = plan.targets[0].fixed_content
        assert "fr" not in fixed  # 舊的 hreflang="fr" 條目已被整組替換
        assert "<lastmod>2026-01-01</lastmod>" in fixed
        assert 'hreflang="en"' in fixed
        assert 'hreflang="zh-TW"' in fixed

    def test_uses_xhtml_prefix_not_generated_ns_prefix(self):
        """xml.etree.ElementTree 若沒有 register_namespace 會自動產生
        ns0/ns1 這類前綴，而不是語意化的 xhtml: —— 這裡鎖住輸出必須用
        正確的 xhtml: 前綴。"""
        plan = build_hreflang_sitemap_plan(_map(), sitemap_path="sitemap.xml", current_sitemap_xml=None)
        fixed = plan.targets[0].fixed_content
        assert "xmlns:xhtml=" in fixed
        assert "<xhtml:link" in fixed
        assert "ns0:" not in fixed
