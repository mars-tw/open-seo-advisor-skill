from seo_advisor.fixers.hreflang_generator import build_hreflang_html_plan
from seo_advisor.fixers.hreflang_map import parse_language_map


def _map_with_targets(targets: dict) -> object:
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
                    "targets": targets,
                }
            ]
        }
    )


class TestBuildHreflangHtmlPlan:
    def test_inserts_after_canonical_when_present(self):
        hmap = _map_with_targets({"en": "en/index.html"})
        pages = {
            "en/index.html": (
                '<html><head><link rel="canonical" href="https://example.com/en/"></head>'
                "<body>Hi</body></html>"
            )
        }
        plan = build_hreflang_html_plan(hmap, pages=pages)
        assert not plan.plan_only
        assert len(plan.targets) == 1
        fixed = plan.targets[0].fixed_content
        canonical_pos = fixed.index('rel="canonical"')
        hreflang_pos = fixed.index('hreflang="en"')
        assert hreflang_pos > canonical_pos

    def test_inserts_after_title_when_no_canonical(self):
        hmap = _map_with_targets({"en": "en/index.html"})
        pages = {"en/index.html": "<html><head><title>Home</title></head><body>Hi</body></html>"}
        plan = build_hreflang_html_plan(hmap, pages=pages)
        fixed = plan.targets[0].fixed_content
        assert fixed.index("</title>") < fixed.index('hreflang="en"')

    def test_replaces_existing_hreflang_tags_entirely(self):
        hmap = _map_with_targets({"en": "en/index.html"})
        pages = {
            "en/index.html": (
                '<html><head><link rel="alternate" hreflang="fr" href="https://old.example.com/fr/">'
                "</head><body>Hi</body></html>"
            )
        }
        plan = build_hreflang_html_plan(hmap, pages=pages)
        fixed = plan.targets[0].fixed_content
        assert "fr" not in fixed
        assert 'hreflang="en"' in fixed
        assert 'hreflang="zh-TW"' in fixed
        assert 'hreflang="x-default"' in fixed

    def test_preserves_non_hreflang_alternate_links(self):
        hmap = _map_with_targets({"en": "en/index.html"})
        pages = {
            "en/index.html": (
                '<html><head><link rel="alternate" type="application/rss+xml" href="/feed.xml">'
                "</head><body>Hi</body></html>"
            )
        }
        plan = build_hreflang_html_plan(hmap, pages=pages)
        fixed = plan.targets[0].fixed_content
        assert "feed.xml" in fixed

    def test_template_syntax_degrades_to_warning_not_target(self):
        hmap = _map_with_targets({"en": "en/index.html"})
        pages = {"en/index.html": "<html><head>{{ site_title }}</head><body>Hi</body></html>"}
        plan = build_hreflang_html_plan(hmap, pages=pages)
        assert plan.targets == []
        assert plan.plan_only
        assert any("樣板" in w for w in plan.warnings)

    def test_missing_head_degrades_to_warning(self):
        hmap = _map_with_targets({"en": "en/index.html"})
        pages = {"en/index.html": "<html><body>no head</body></html>"}
        plan = build_hreflang_html_plan(hmap, pages=pages)
        assert plan.targets == []
        assert plan.plan_only
        assert any("<head>" in w for w in plan.warnings)

    def test_missing_page_content_degrades_to_warning(self):
        hmap = _map_with_targets({"en": "en/index.html"})
        plan = build_hreflang_html_plan(hmap, pages={})
        assert plan.targets == []
        assert plan.plan_only

    def test_cluster_without_targets_produces_plan_only_with_suggested_tags(self):
        hmap = _map_with_targets({})
        plan = build_hreflang_html_plan(hmap, pages={})
        assert plan.plan_only
        assert any("targets" in w for w in plan.warnings)
        assert any("hreflang" in action for action in plan.suggested_actions)

    def test_disallowed_write_extension_degrades_to_warning(self):
        hmap = _map_with_targets({"en": "en/index.php"})
        pages = {"en/index.php": "<html><head></head><body>Hi</body></html>"}
        plan = build_hreflang_html_plan(hmap, pages=pages)
        assert plan.targets == []
        assert plan.plan_only

    def test_plan_id_and_finding_id_are_generator_specific(self):
        hmap = _map_with_targets({"en": "en/index.html"})
        pages = {"en/index.html": "<html><head></head><body>Hi</body></html>"}
        plan = build_hreflang_html_plan(hmap, pages=pages)
        assert "hreflang" in plan.plan_id
        assert plan.fix_type == "hreflang_generate_html"

    def test_multiple_languages_in_same_cluster_all_produce_targets(self):
        hmap = _map_with_targets({"en": "en/index.html", "zh-TW": "zh/index.html"})
        pages = {
            "en/index.html": "<html><head></head><body>Hi</body></html>",
            "zh/index.html": "<html><head></head><body>嗨</body></html>",
        }
        plan = build_hreflang_html_plan(hmap, pages=pages)
        assert len(plan.targets) == 2
        paths = {t.path for t in plan.targets}
        assert paths == {"en/index.html", "zh/index.html"}
