"""Google Search indexing directives and hreflang syntax shared by SEO tools."""

import re

from bs4 import BeautifulSoup

_HREFLANG = re.compile(r"[a-z]{2}(?:-[a-z]{4})?(?:-[a-z]{2})?", re.ASCII | re.I)
_PARAMETERIZED_RULES = {
    "max-snippet",
    "max-image-preview",
    "max-video-preview",
    "unavailable_after",
}


def valid_hreflang(code: str) -> bool:
    """Check the language[-script][-region] format, not registry membership."""
    return code.casefold() == "x-default" or bool(_HREFLANG.fullmatch(code))


def google_noindex(soup: BeautifulSoup | None, headers=None) -> list[str]:
    """Return each applicable noindex/none declaration with its source.

    Separate X-Robots-Tag fields reset the crawler scope. Accept httpx.Headers,
    a plain mapping, or mapping values containing the individual header fields.
    """
    matches = []
    if soup is not None:
        for tag in soup.find_all("meta", attrs={"name": True, "content": True}):
            name = tag["name"].strip().casefold()
            content = tag["content"]
            if name in {"robots", "googlebot"} and _restricts_indexing(content):
                matches.append(f"meta {name}: {content}")

    if hasattr(headers, "get_list"):
        values = headers.get_list("x-robots-tag")
    else:
        values = []
        for name, value in (headers or {}).items():
            if name.casefold() == "x-robots-tag":
                values.extend([value] if isinstance(value, str) else value)
    for value in values:
        agent = "*"
        for part in value.split(","):
            directive = part.strip()
            prefix, colon, rest = directive.partition(":")
            prefix = prefix.strip().casefold()
            if (
                colon
                and re.fullmatch(r"[a-z0-9_*-]+", prefix)
                and prefix not in _PARAMETERIZED_RULES
            ):
                agent, directive = prefix, rest.strip()
            if agent in {"*", "googlebot"} and _restricts_indexing(directive):
                matches.append(f"X-Robots-Tag ({agent}): {directive}")
    return matches


def _restricts_indexing(content: str) -> bool:
    # "max-image-preview: none" governs previews, not indexing.
    return any(
        {"noindex", "none"}.intersection(part.casefold().split())
        for part in content.split(",")
        if ":" not in part
    )
