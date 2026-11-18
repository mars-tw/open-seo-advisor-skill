import httpx
import pytest
from bs4 import BeautifulSoup

from seo_advisor.indexability import google_noindex, valid_hreflang


@pytest.mark.parametrize(
    "code, valid",
    [
        ("zh-Hant", True),
        ("zh-Hans-CN", True),
        ("en-GB", True),
        ("x-default", True),
        ("zh_TW", False),
        ("zh-TW-Hant", False),
        ("latin", False),
        ("en--US", False),
    ],
)
def test_hreflang_language_script_region(code, valid):
    assert valid_hreflang(code) is valid


def test_index_directives_keep_http_field_scope_and_ignore_preview_limits():
    soup = BeautifulSoup(
        '<meta name="robots" content="index,follow"><meta name="GoogleBot" content="none">'
        '<meta name="anotherbot" content="noindex">',
        "html.parser",
    )
    headers = httpx.Headers(
        [
            ("X-Robots-Tag", "anotherbot: nofollow, noindex"),
            ("X-Robots-Tag", "max-image-preview: none, noindex"),
        ]
    )
    assert google_noindex(soup, headers) == ["meta googlebot: none", "X-Robots-Tag (*): noindex"]
    assert google_noindex(None, {"X-Robots-Tag": "otherbot: none, noindex"}) == []
    assert google_noindex(None, {"x-robots-tag": ["otherbot: noindex", "googlebot: none"]})
    assert google_noindex(None, {"x-robots-tag": "max-image-preview: none"}) == []
    assert google_noindex(
        None, {"X-Robots-Tag": "unavailable_after: Fri, 25 Jun 2021 15:00:00 PST, noindex"}
    )
