"""Security Mode 其餘檢查模組測試：spam/cms/https_check（憑證檢查獨立測試在
別處，因為需要真實 socket 連線，這裡只測不需要網路連線的部分）。"""

from collections import Counter

from seo_advisor.security_mode import cms, https_check, spam


def _next_id_factory():
    counter: Counter[str] = Counter()

    def next_id(category: str) -> str:
        counter[category] += 1
        return f"SEC-{category.upper()}-{counter[category]:03d}"

    return next_id


# --- spam.py ---


def test_hidden_content_with_suspicious_keyword_flagged_higher_severity():
    html = (
        '<html><body><a href="/x" style="display:none">buy cheap viagra online</a>'
        "<p>Normal visible content</p></body></html>"
    )
    findings = spam.check_seo_spam(html, "https://example.com", _next_id_factory())
    assert len(findings) == 1
    assert findings[0].severity.value == "S1"
    assert findings[0].needs_credential_rotation is True


def test_hidden_content_without_suspicious_keyword_is_lower_severity():
    html = '<html><body><span style="visibility:hidden">screen reader only text</span></body></html>'
    findings = spam.check_seo_spam(html, "https://example.com", _next_id_factory())
    assert len(findings) == 1
    assert findings[0].severity.value == "S2"
    assert findings[0].needs_credential_rotation is False


def test_normal_page_without_hidden_elements_is_not_flagged():
    html = "<html><body><p>Just a normal page.</p></body></html>"
    findings = spam.check_seo_spam(html, "https://example.com", _next_id_factory())
    assert findings == []


def test_empty_html_is_not_flagged():
    assert spam.check_seo_spam("", "https://example.com", _next_id_factory()) == []


# --- cms.py ---


def test_wordpress_version_exposure_detected():
    html = '<html><head><meta name="generator" content="WordPress 6.2.1"></head></html>'
    findings = cms.check_cms_version_exposure(html, "https://example.com", _next_id_factory())
    assert len(findings) == 1
    assert "6.2.1" in findings[0].title
    assert findings[0].evidence["version"] == "6.2.1"


def test_generic_generator_tag_detected_when_not_wordpress():
    html = '<html><head><meta name="generator" content="Hugo 0.120"></head></html>'
    findings = cms.check_cms_version_exposure(html, "https://example.com", _next_id_factory())
    assert len(findings) == 1
    assert "Hugo" in findings[0].evidence["generator"]


def test_no_generator_tag_produces_no_finding():
    html = "<html><head><title>Test</title></head></html>"
    findings = cms.check_cms_version_exposure(html, "https://example.com", _next_id_factory())
    assert findings == []


# --- https_check.py（不需要網路連線的部分）---


def test_non_https_scheme_flagged_as_high_severity():
    findings = https_check.check_certificate("http://example.com", _next_id_factory())
    assert len(findings) == 1
    assert findings[0].severity.value == "S1"
    assert findings[0].category == "https"


def test_hsts_missing_flagged_for_https_url():
    findings = https_check.check_hsts({}, "https://example.com", _next_id_factory())
    assert len(findings) == 1
    assert findings[0].severity.value == "S3"


def test_hsts_present_produces_no_finding():
    findings = https_check.check_hsts(
        {"strict-transport-security": "max-age=31536000"}, "https://example.com", _next_id_factory()
    )
    assert findings == []


def test_hsts_check_skipped_for_http_url():
    findings = https_check.check_hsts({}, "http://example.com", _next_id_factory())
    assert findings == []


def test_mixed_content_detected_for_http_assets_on_https_page():
    html = '<html><body><img src="http://example.com/logo.png"></body></html>'
    findings = https_check.check_mixed_content(html, "https://example.com", _next_id_factory())
    assert len(findings) == 1
    assert findings[0].evidence["count"] == 1


def test_mixed_content_not_flagged_for_all_https_assets():
    html = '<html><body><img src="https://example.com/logo.png"></body></html>'
    findings = https_check.check_mixed_content(html, "https://example.com", _next_id_factory())
    assert findings == []


def test_mixed_content_check_skipped_for_http_page():
    html = '<html><body><img src="http://example.com/logo.png"></body></html>'
    findings = https_check.check_mixed_content(html, "http://example.com", _next_id_factory())
    assert findings == []
