"""Discover declared sitemaps within the current connector's crawl scope."""

from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse
from xml.etree import ElementTree

from seo_advisor.models import UrlRecord

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
MAX_FILES = 50


@dataclass
class SitemapResult:
    documents: dict[str, str] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    records: list[UrlRecord] = field(default_factory=list)


def sitemap_candidates(seed, robots, in_scope):
    candidates = {}
    for line in (robots or "").splitlines():
        field_name, separator, value = line.split("#", 1)[0].partition(":")
        if not separator or field_name.strip().lower() != "sitemap" or not value.strip():
            continue
        try:
            url = urldefrag(urljoin(seed, value.strip())).url
        except ValueError:
            continue
        if urlparse(url).scheme in {"", "http", "https"} and in_scope(url):
            candidates[url] = "robots.txt"
            if len(candidates) >= MAX_FILES:
                break
    candidates.setdefault(urljoin(seed, "/sitemap.xml"), "conventional")
    return candidates


def sitemap_root(body):
    lowered = body.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise ValueError("sitemap contains a document type or entity declaration")
    return ElementTree.fromstring(body)


def absolute_web_url(value):
    try:
        parsed = urlparse(value)
        return bool(parsed.scheme in {"http", "https"} and parsed.hostname)
    except ValueError:
        return False


def read_sitemaps(seed, robots, in_scope, fetch, limit):
    result = SitemapResult()
    queue = deque(
        (url, source, 0) for url, source in sitemap_candidates(seed, robots, in_scope).items()
    )
    seen_pages = set()
    found_root = False
    while queue and len(result.sources) < MAX_FILES:
        url, source, depth = queue.popleft()
        if url in result.sources or (source == "conventional" and found_root):
            continue
        result.sources[url] = source
        body = fetch(url)
        if body is None:
            continue
        result.documents[url] = body
        try:
            root = sitemap_root(body)
        except (ElementTree.ParseError, ValueError):
            continue
        if root.tag not in {NS + "urlset", NS + "sitemapindex"}:
            continue
        found_root = True
        index = root.tag == NS + "sitemapindex"
        for entry in root.iterfind(NS + ("sitemap" if index else "url")):
            target = (entry.findtext(NS + "loc") or "").strip()
            if not absolute_web_url(target) or not in_scope(target):
                continue
            parsed = urlparse(target)
            target = parsed._replace(
                netloc=parsed.netloc.lower(), path=parsed.path or "/", fragment=""
            ).geturl()
            if index:
                if depth < 2 and len(queue) < MAX_FILES and target not in result.sources:
                    queue.append((target, url, depth + 1))
            elif len(result.records) < limit and target not in seen_pages:
                seen_pages.add(target)
                result.records.append(
                    UrlRecord(url=target, source="sitemap", discovered_depth=depth)
                )
    return result
