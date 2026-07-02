import pytest

from seo_advisor.url_utils import InvalidUrlError, normalize_url


def test_bare_domain_gets_https_prefix():
    assert normalize_url("example.com") == "https://example.com"


def test_www_domain_gets_https_prefix():
    assert normalize_url("www.example.com") == "https://www.example.com"


def test_explicit_https_is_preserved():
    assert normalize_url("https://example.com") == "https://example.com"


def test_explicit_http_is_preserved():
    assert normalize_url("http://example.com") == "http://example.com"


def test_strips_surrounding_whitespace():
    assert normalize_url("  example.com  ") == "https://example.com"


def test_empty_string_raises_invalid_url_error():
    with pytest.raises(InvalidUrlError):
        normalize_url("")


def test_gibberish_raises_invalid_url_error():
    with pytest.raises(InvalidUrlError):
        normalize_url("not a url at all")


def test_localhost_is_accepted():
    assert normalize_url("localhost") == "https://localhost"


def test_subdomain_and_path_supported():
    assert normalize_url("shop.example.co.uk") == "https://shop.example.co.uk"


def test_url_with_embedded_credentials_is_rejected():
    with pytest.raises(InvalidUrlError):
        normalize_url("https://user:pass@example.com")


def test_url_with_username_only_is_rejected():
    with pytest.raises(InvalidUrlError):
        normalize_url("https://admin@example.com")


def test_looks_like_url_distinguishes_url_from_goal():
    from seo_advisor.url_utils import looks_like_url

    assert looks_like_url("example.com") is True
    assert looks_like_url("www.example.com") is True
    assert looks_like_url("https://example.com") is True
    assert looks_like_url("幫我規劃成長方案") is False
    assert looks_like_url("optimize my amazon listing") is False  # 含空白 → 目標描述
    assert looks_like_url("") is False
