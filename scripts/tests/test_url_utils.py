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
