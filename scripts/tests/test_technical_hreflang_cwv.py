"""測試新增的技術 SEO 檢查：hreflang（self-reference/重複/格式/互相對稱/
授權範圍外/HTML+sitemap 混用）與 CWV 靜態線索（img 缺尺寸/blocking script）。
"""

from __future__ import annotations

from seo_advisor.analyzers.technical import analyze_technical_seo
from seo_advisor.crawler import CrawlResult
from seo_advisor.models import PageSnapshot


def _page(url: str, html: str, status: int = 200) -> PageSnapshot:
    return PageSnapshot(
        url=url, status_code=status, final_url=url,
        headers={"content-type": "text/html"}, html=html, fetched_at="t",
    )


def _result(pages: dict[str, str], sitemap_xml: str | None = None) -> CrawlResult:
    return CrawlResult(
        pages={url: _page(url, html) for url, html in pages.items()},
        sitemap_xml=sitemap_xml,
    )


class TestHreflangMissingSelfReference:
    def test_flags_page_without_self_reference(self):
        html = (
            '<html><head>'
            '<link rel="alternate" hreflang="en" href="https://example.com/en">'
            '</head><body>hi</body></html>'
        )
        result = _result({"https://example.com/zh": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/zh")
        assert any("HREFLANG_MISSING_SELF_REFERENCE" in f.id for f in findings)

    def test_does_not_flag_page_with_self_reference(self):
        html = (
            '<html><head>'
            '<link rel="alternate" hreflang="zh-TW" href="https://example.com/zh">'
            '<link rel="alternate" hreflang="en" href="https://example.com/en">'
            '</head><body>hi</body></html>'
        )
        result = _result({
            "https://example.com/zh": html,
            "https://example.com/en": (
                '<html><head>'
                '<link rel="alternate" hreflang="zh-TW" href="https://example.com/zh">'
                '<link rel="alternate" hreflang="en" href="https://example.com/en">'
                '</head><body>hi</body></html>'
            ),
        })
        findings = analyze_technical_seo(result, seed_url="https://example.com/zh")
        assert not any("HREFLANG_MISSING_SELF_REFERENCE" in f.id for f in findings)

    def test_pages_without_hreflang_not_flagged(self):
        html = "<html><head><title>t</title></head><body>hi</body></html>"
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert not any("HREFLANG" in f.id for f in findings)


class TestHreflangDuplicateLanguage:
    def test_flags_duplicate_language_code(self):
        html = (
            '<html><head>'
            '<link rel="alternate" hreflang="en" href="https://example.com/en">'
            '<link rel="alternate" hreflang="en" href="https://example.com/en-2">'
            '</head><body>hi</body></html>'
        )
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert any("HREFLANG_DUPLICATE_LANGUAGE" in f.id for f in findings)


class TestHreflangInvalidCode:
    def test_flags_invalid_format(self):
        html = (
            '<html><head>'
            '<link rel="alternate" hreflang="english" href="https://example.com/en">'
            '</head><body>hi</body></html>'
        )
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert any("HREFLANG_INVALID_CODE" in f.id for f in findings)

    def test_does_not_flag_valid_language_only_code(self):
        html = (
            '<html><head>'
            '<link rel="alternate" hreflang="en" href="https://example.com/x">'
            '</head><body>hi</body></html>'
        )
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert not any("HREFLANG_INVALID_CODE" in f.id for f in findings)

    def test_does_not_flag_valid_language_region_code(self):
        html = (
            '<html><head>'
            '<link rel="alternate" hreflang="zh-TW" href="https://example.com/x">'
            '</head><body>hi</body></html>'
        )
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert not any("HREFLANG_INVALID_CODE" in f.id for f in findings)

    def test_does_not_flag_x_default(self):
        html = (
            '<html><head>'
            '<link rel="alternate" hreflang="x-default" href="https://example.com/x">'
            '</head><body>hi</body></html>'
        )
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert not any("HREFLANG_INVALID_CODE" in f.id for f in findings)

    def test_does_not_validate_real_language_existence(self):
        """格式正確但語言代碼不存在（zz 不是真實 ISO 639-1 代碼）不應被抓出——
        這輪只做格式粗檢，不維護完整語言代碼對照表。"""
        html = (
            '<html><head>'
            '<link rel="alternate" hreflang="zz-ZZ" href="https://example.com/x">'
            '</head><body>hi</body></html>'
        )
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert not any("HREFLANG_INVALID_CODE" in f.id for f in findings)


class TestHreflangOutOfScope:
    def test_flags_cross_domain_target(self):
        html = (
            '<html><head>'
            '<link rel="alternate" hreflang="en" href="https://totally-different.com/en">'
            '</head><body>hi</body></html>'
        )
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert any("HREFLANG_OUT_OF_SCOPE" in f.id for f in findings)

    def test_does_not_flag_same_domain_target(self):
        html = (
            '<html><head>'
            '<link rel="alternate" hreflang="en" href="https://example.com/en">'
            '</head><body>hi</body></html>'
        )
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert not any("HREFLANG_OUT_OF_SCOPE" in f.id for f in findings)


class TestHreflangNonReciprocal:
    def test_flags_one_directional_reference(self):
        page_a = (
            '<html><head>'
            '<link rel="alternate" hreflang="zh-TW" href="https://example.com/zh">'
            '<link rel="alternate" hreflang="en" href="https://example.com/en">'
            '</head><body>hi</body></html>'
        )
        # /en 完全沒有 hreflang 宣告，不會指回 /zh。
        page_b = "<html><head><title>English page</title></head><body>hi</body></html>"
        result = _result({
            "https://example.com/zh": page_a,
            "https://example.com/en": page_b,
        })
        findings = analyze_technical_seo(result, seed_url="https://example.com/zh")
        assert any("HREFLANG_NON_RECIPROCAL" in f.id for f in findings)

    def test_does_not_flag_reciprocal_pair(self):
        page_a = (
            '<html><head>'
            '<link rel="alternate" hreflang="zh-TW" href="https://example.com/zh">'
            '<link rel="alternate" hreflang="en" href="https://example.com/en">'
            '</head><body>hi</body></html>'
        )
        page_b = (
            '<html><head>'
            '<link rel="alternate" hreflang="zh-TW" href="https://example.com/zh">'
            '<link rel="alternate" hreflang="en" href="https://example.com/en">'
            '</head><body>hi</body></html>'
        )
        result = _result({
            "https://example.com/zh": page_a,
            "https://example.com/en": page_b,
        })
        findings = analyze_technical_seo(result, seed_url="https://example.com/zh")
        assert not any("HREFLANG_NON_RECIPROCAL" in f.id for f in findings)

    def test_does_not_flag_when_target_page_not_crawled(self):
        """目標頁沒有被本次 crawl 抓到時，不應誤判成「沒有指回來」——
        無法驗證的情況不等於確認有問題。"""
        page_a = (
            '<html><head>'
            '<link rel="alternate" hreflang="zh-TW" href="https://example.com/zh">'
            '<link rel="alternate" hreflang="en" href="https://example.com/en">'
            '</head><body>hi</body></html>'
        )
        # /en 根本不在這次 crawl 的 pages 裡（例如爬蟲深度限制沒抓到）。
        result = _result({"https://example.com/zh": page_a})
        findings = analyze_technical_seo(result, seed_url="https://example.com/zh")
        assert not any("HREFLANG_NON_RECIPROCAL" in f.id for f in findings)


class TestHreflangMixedImplementation:
    def test_flags_when_sitemap_also_has_hreflang(self):
        html = (
            '<html><head>'
            '<link rel="alternate" hreflang="en" href="https://example.com/en">'
            '</head><body>hi</body></html>'
        )
        sitemap_with_hreflang = (
            '<?xml version="1.0"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml">'
            '<url><loc>https://example.com/en</loc>'
            '<xhtml:link rel="alternate" hreflang="en" href="https://example.com/en"/>'
            "</url></urlset>"
        )
        result = _result({"https://example.com/en": html}, sitemap_xml=sitemap_with_hreflang)
        findings = analyze_technical_seo(result, seed_url="https://example.com/en")
        assert any("HREFLANG_MIXED_IMPLEMENTATION" in f.id for f in findings)

    def test_does_not_flag_when_sitemap_has_no_hreflang(self):
        html = (
            '<html><head>'
            '<link rel="alternate" hreflang="en" href="https://example.com/en">'
            '</head><body>hi</body></html>'
        )
        plain_sitemap = (
            '<?xml version="1.0"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            "<url><loc>https://example.com/en</loc></url></urlset>"
        )
        result = _result({"https://example.com/en": html}, sitemap_xml=plain_sitemap)
        findings = analyze_technical_seo(result, seed_url="https://example.com/en")
        assert not any("HREFLANG_MIXED_IMPLEMENTATION" in f.id for f in findings)


class TestCwvImageMissingDimensions:
    def test_flags_img_without_width_height(self):
        html = '<html><body><img src="a.jpg"></body></html>'
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert any("IMAGE_MISSING_DIMENSIONS_HINT" in f.id for f in findings)

    def test_does_not_flag_img_with_both_dimensions(self):
        html = '<html><body><img src="a.jpg" width="100" height="100"></body></html>'
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert not any("IMAGE_MISSING_DIMENSIONS_HINT" in f.id for f in findings)

    def test_flags_when_only_one_dimension_present(self):
        html = '<html><body><img src="a.jpg" width="100"></body></html>'
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert any("IMAGE_MISSING_DIMENSIONS_HINT" in f.id for f in findings)

    def test_no_images_not_flagged(self):
        html = "<html><body><p>no images here</p></body></html>"
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert not any("IMAGE_MISSING_DIMENSIONS_HINT" in f.id for f in findings)


class TestCwvBlockingScripts:
    def test_flags_three_or_more_blocking_scripts(self):
        html = (
            "<html><body>"
            '<script src="a.js"></script>'
            '<script src="b.js"></script>'
            '<script src="c.js"></script>'
            "</body></html>"
        )
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert any("BLOCKING_SCRIPTS_HINT" in f.id for f in findings)

    def test_does_not_flag_two_blocking_scripts(self):
        html = (
            "<html><body>"
            '<script src="a.js"></script>'
            '<script src="b.js"></script>'
            "</body></html>"
        )
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert not any("BLOCKING_SCRIPTS_HINT" in f.id for f in findings)

    def test_does_not_flag_scripts_with_defer(self):
        html = (
            "<html><body>"
            '<script src="a.js" defer></script>'
            '<script src="b.js" defer></script>'
            '<script src="c.js" defer></script>'
            "</body></html>"
        )
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert not any("BLOCKING_SCRIPTS_HINT" in f.id for f in findings)

    def test_does_not_flag_scripts_with_async(self):
        html = (
            "<html><body>"
            '<script src="a.js" async></script>'
            '<script src="b.js" async></script>'
            '<script src="c.js" async></script>'
            "</body></html>"
        )
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert not any("BLOCKING_SCRIPTS_HINT" in f.id for f in findings)

    def test_inline_scripts_not_counted(self):
        html = (
            "<html><body>"
            "<script>console.log(1)</script>"
            "<script>console.log(2)</script>"
            "<script>console.log(3)</script>"
            "</body></html>"
        )
        result = _result({"https://example.com/x": html})
        findings = analyze_technical_seo(result, seed_url="https://example.com/x")
        assert not any("BLOCKING_SCRIPTS_HINT" in f.id for f in findings)
