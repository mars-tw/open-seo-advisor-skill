from __future__ import annotations

import re
import xml.dom.minidom as minidom
from html.parser import HTMLParser

from seo_advisor.models import Finding, Mode, Report, ReportTarget, Severity
from seo_advisor.report_html import render_html


class _StrictHtmlChecker(HTMLParser):
    def error(self, message):
        raise ValueError(message)


def _assert_valid_html(html: str) -> None:
    _StrictHtmlChecker().feed(html)


def _assert_svgs_well_formed(html: str) -> None:
    for svg in re.findall(r"<svg.*?</svg>", html, re.DOTALL):
        minidom.parseString(svg)


def _finding(**overrides) -> Finding:
    defaults = dict(
        id="SEO-TEST-001",
        title="測試發現",
        mode=Mode.CONSULTANT,
        category="indexability",
        severity=Severity.P1,
        impact=3,
        effort=2,
        confidence=0.8,
        affected_urls=["https://example.com/a"],
        evidence={},
        recommendation="修好它",
        validation=[],
    )
    defaults.update(overrides)
    return Finding(**defaults)


def _report(findings: list[Finding] | None = None, scan_stats: dict | None = None) -> Report:
    findings = findings if findings is not None else [_finding()]
    return Report(
        report_id="r-1",
        generated_at="2026-07-13T00:00:00Z",
        target=ReportTarget(source_type="http", identifier="https://example.com"),
        mode=Mode.CONSULTANT,
        executive_summary="測試摘要",
        site_health_score=80,
        findings=findings,
        top_findings=[f.id for f in findings],
        coverage_notes=["只掃描前 200 個 URL"],
        scan_stats=scan_stats if scan_stats is not None else {},
    )


class TestRenderHtmlBasics:
    def test_produces_valid_html_document(self):
        html = render_html(_report())
        _assert_valid_html(html)
        assert html.startswith("<!doctype html>")

    def test_includes_target_and_health_score(self):
        html = render_html(_report())
        assert "https://example.com" in html
        assert "80" in html

    def test_no_findings_does_not_crash(self):
        html = render_html(_report(findings=[]))
        _assert_valid_html(html)
        assert "沒有" in html or "無" in html


class TestHtmlEscaping:
    def test_escapes_finding_title(self):
        finding = _finding(title='<script>alert(1)</script>')
        html = render_html(_report(findings=[finding]))
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_escapes_executive_summary(self):
        report = _report()
        report.executive_summary = '<img src=x onerror=alert(1)>'
        html = render_html(report)
        assert "<img src=x" not in html
        assert "&lt;img" in html

    def test_escapes_affected_urls(self):
        finding = _finding(affected_urls=['https://example.com/"><script>alert(1)</script>'])
        html = render_html(_report(findings=[finding]))
        assert "<script>alert(1)</script>" not in html

    def test_escapes_recommendation_and_validation(self):
        finding = _finding(
            recommendation='<b>bold</b> recommendation',
            validation=['<i>check</i> this'],
        )
        html = render_html(_report(findings=[finding]))
        assert "<b>bold</b>" not in html
        assert "<i>check</i>" not in html

    def test_escapes_coverage_notes(self):
        report = _report()
        report.coverage_notes = ['<script>evil()</script>']
        html = render_html(report)
        assert "<script>evil()</script>" not in html

    def test_escapes_scan_stats_values(self):
        html = render_html(_report(scan_stats={"detected_stack": "<script>x</script>"}))
        assert "<script>x</script>" not in html

    def test_escapes_hreflang_matrix_urls(self):
        scan_stats = {
            "hreflang_matrix": {
                '<script>alert(1)</script>': {"en": '<script>alert(2)</script>'},
            }
        }
        html = render_html(_report(scan_stats=scan_stats))
        assert "<script>alert(1)</script>" not in html
        assert "<script>alert(2)</script>" not in html

    def test_escapes_svg_circle_title_tooltip(self):
        """Impact x Effort 圖表的每個點用 <title> 當 SVG tooltip，這裡的
        finding.title 是使用者/爬取來源可影響的內容，必須跳脫。"""
        finding = _finding(title='</title><script>alert(1)</script>')
        html = render_html(_report(findings=[finding]))
        assert "<script>alert(1)</script>" not in html

    def test_no_anchor_tags_with_unescaped_href(self):
        """報告裡的 URL 一律只顯示為純文字，不做成可點擊連結——避免
        `javascript:` 之類的 href scheme 被爬取來源的內容注入。"""
        finding = _finding(affected_urls=["javascript:alert(1)"])
        html = render_html(_report(findings=[finding]))
        assert "<a " not in html
        assert "href=" not in html


class TestImpactEffortChart:
    def test_chart_present_with_findings(self):
        html = render_html(_report())
        assert "Impact x Effort" in html
        _assert_svgs_well_formed(html)

    def test_chart_has_one_point_per_finding(self):
        findings = [_finding(id=f"F-{i}", impact=i % 5 + 1, effort=(i + 2) % 5 + 1) for i in range(5)]
        html = render_html(_report(findings=findings))
        assert html.count("<circle") == 5

    def test_empty_findings_shows_placeholder_not_broken_chart(self):
        html = render_html(_report(findings=[]))
        assert "Impact x Effort" in html
        assert "<circle" not in html


class TestStatusDistributionChart:
    def test_renders_bars_when_data_present(self):
        scan_stats = {"status_code_distribution": {"2xx": 10, "3xx": 2, "4xx": 1, "5xx": 0, "0": 0}}
        html = render_html(_report(scan_stats=scan_stats))
        _assert_svgs_well_formed(html)
        assert "URL 狀態分布" in html

    def test_missing_data_shows_explanatory_message_not_crash(self):
        html = render_html(_report(scan_stats={}))
        assert "此版本報告未提供狀態碼分布資料" in html


class TestHreflangMatrix:
    def test_renders_table_when_data_present(self):
        scan_stats = {
            "hreflang_matrix": {
                "https://example.com/en": {"en": "https://example.com/en", "zh-TW": "https://example.com/zh"},
                "https://example.com/zh": {"en": "https://example.com/en", "zh-TW": "https://example.com/zh"},
            }
        }
        html = render_html(_report(scan_stats=scan_stats))
        assert "hreflang 矩陣" in html
        # class="hreflang-yes" 這個字串本身也出現在 <style> 裡的 CSS 規則
        # 定義（.hreflang-yes { ... }），因此用 <td class="hreflang-yes" 這個
        # 更完整的前綴精確鎖定表格儲存格，避免誤把 CSS 規則也算進計數。
        assert html.count('<td class="hreflang-yes"') == 4  # 2 頁 x 2 語言

    def test_section_absent_when_no_data(self):
        html = render_html(_report(scan_stats={}))
        assert "hreflang 矩陣" not in html

    def test_x_default_sorted_last(self):
        scan_stats = {
            "hreflang_matrix": {
                "https://example.com/": {
                    "zh-TW": "https://example.com/zh",
                    "x-default": "https://example.com/",
                    "en": "https://example.com/en",
                }
            }
        }
        html = render_html(_report(scan_stats=scan_stats))
        thead = html[html.index("<thead>") : html.index("</thead>")]
        en_pos = thead.index(">en<")
        zh_pos = thead.index(">zh-TW<")
        default_pos = thead.index(">x-default<")
        assert en_pos < zh_pos < default_pos


class TestFindingsList:
    def test_affected_urls_truncated_with_count_note(self):
        finding = _finding(affected_urls=[f"https://example.com/{i}" for i in range(20)])
        html = render_html(_report(findings=[finding]))
        assert "（等共 20 個）" in html

    def test_full_findings_list_capped(self):
        findings = [_finding(id=f"SEO-TEST-{i:03d}") for i in range(250)]
        html = render_html(_report(findings=findings, scan_stats={}))
        assert "report.json" in html  # 截斷提示
        _assert_valid_html(html)


class TestAppendix:
    def test_scan_stats_listed_excluding_hreflang_matrix_raw_dump(self):
        scan_stats = {
            "urls_crawled": 10,
            "hreflang_matrix": {"https://example.com/": {"en": "https://example.com/en"}},
        }
        html = render_html(_report(scan_stats=scan_stats))
        assert "urls_crawled" in html
        # hreflang_matrix 的完整原始 dict 不該在附錄重複傾印一次
        appendix_start = html.index("掃描統計")
        appendix_html = html[appendix_start:]
        assert "hreflang_matrix" not in appendix_html
