"""Read sitemap protocols and record the scope of a bounded discovery pass."""

import gzip
import io
import zlib
from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse
from xml.etree import ElementTree

from seo_advisor.models import UrlRecord
from seo_advisor.robots_rules import robots_fields

NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
ATOM = "{http://www.w3.org/2005/Atom}"
XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"
MAX_FILES = 50  # Maximum child files, independent of root declarations.
MAX_URLS_PER_FILE = 50_000
MAX_BYTES = 50 * 1024 * 1024


@dataclass
class SitemapFetch:
    status: int
    body: str | None = None
    error: str = ""
    limited: bool = False
    final_url: str = ""


def decode_sitemap_bytes(raw: bytes, status: int = 200) -> SitemapFetch:
    try:
        if raw.startswith(b"\x1f\x8b"):
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return SitemapFetch(status, error="解壓後超過 sitemap 的 50 MiB 上限")
        return SitemapFetch(status, raw.decode("utf-8-sig"))
    except (EOFError, OSError, zlib.error, UnicodeDecodeError) as exc:
        return SitemapFetch(status, error=f"無法讀取 gzip 或 UTF-8 內容（{type(exc).__name__}）")


@dataclass
class SitemapResult:
    documents: dict[str, str] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)
    statuses: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    pending: dict[str, str] = field(default_factory=dict)
    records: list[UrlRecord] = field(default_factory=list)
    document_bases: dict[str, str] = field(default_factory=dict)
    relative_feeds: list[str] = field(default_factory=list)


def sitemap_candidates(seed, robots):
    candidates = {}
    for key, value in robots_fields(robots or ""):
        if key == "sitemap" and value:
            try:
                url = urldefrag(urljoin(seed, value)).url
                if urlparse(url).scheme in {"", "http", "https"}:
                    candidates[url] = "robots.txt"
            except ValueError:
                continue
    candidates.setdefault(urljoin(seed, "/sitemap.xml"), "conventional")
    return candidates


def absolute_web_url(value):
    try:
        parsed = urlparse(value)
        return bool(
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and not any(c.isspace() for c in value)
        )
    except ValueError:
        return False


def _resolve_atom(base, reference):
    try:
        return urljoin(base, reference)
    except ValueError:
        return ""


@dataclass
class SitemapContent:
    kind: str = ""
    urls: list[str] = field(default_factory=list)
    count: int = 0
    problem: str = ""
    category: str = "sitemap_invalid_structure"
    relative_links: bool = False

    def add(self, value):
        self.count += 1
        value = (value or "").strip()
        if absolute_web_url(value):
            self.urls.append(value)
        elif not self.problem:
            self.problem = f"第 {self.count} 筆缺少完整的 HTTP(S) 網址"


def parse_sitemap(body: str, document_url: str = "") -> SitemapContent:
    """Return the same interpretation to both page discovery and the audit."""
    body = body.removeprefix("\ufeff").strip()
    doc = SitemapContent()
    if body and not body.startswith("<"):
        doc.kind = "text"
        for line in body.splitlines():
            if line.strip():
                doc.add(line)
    else:
        lowered = body.lower()
        if "<!doctype" in lowered or "<!entity" in lowered:
            doc.problem = "sitemap 包含不適用的文件型別或實體宣告"
            return doc
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError as exc:
            doc.category = "sitemap_invalid_xml"
            doc.problem = str(exc)
            return doc
        if root.tag in {NS + "urlset", NS + "sitemapindex"}:
            doc.kind = "index" if root.tag == NS + "sitemapindex" else "urlset"
            entry_tag = NS + ("sitemap" if doc.kind == "index" else "url")
            for entry in root:
                locations = entry.findall(NS + "loc")
                doc.add(locations[0].text if entry.tag == entry_tag and len(locations) == 1 else "")
        elif root.tag == ATOM + "feed":
            doc.kind = "atom"
            feed_base = _resolve_atom(document_url, root.get(XML_BASE, ""))
            for entry in root.findall(ATOM + "entry"):
                entry_base = _resolve_atom(feed_base, entry.get(XML_BASE, ""))
                alternates = [link for link in entry.findall(ATOM + "link")
                              if link.get("rel", "alternate") == "alternate"]
                if not alternates:
                    doc.add("")
                for link in alternates:
                    href = (link.get("href") or "").strip()
                    link_base = _resolve_atom(entry_base, link.get(XML_BASE, ""))
                    resolved = _resolve_atom(link_base, href) if href else ""
                    if absolute_web_url(resolved) and not absolute_web_url(href):
                        doc.relative_links = True
                    doc.add(resolved)
        elif (
            root.tag == "rss" and root.get("version") == "2.0" and root.find("channel") is not None
        ):
            doc.kind = "rss"
            for item in root.findall("channel/item"):
                value = item.findtext("link")
                guid = item.find("guid")
                if (
                    not value
                    and guid is not None
                    and guid.get("isPermaLink", "true").lower() == "true"
                ):
                    value = guid.text
                doc.add(value)
        else:
            doc.problem = "根元素不符合 sitemap XML、RSS 2.0 或 Atom 1.0"
            return doc
    if doc.count > MAX_URLS_PER_FILE:
        doc.category = "sitemap_too_large"
        doc.problem = f"檔案含 {doc.count} 筆，單檔上限為 50,000 筆"
    elif not doc.count and not doc.problem:
        doc.problem = "缺少網址或子 sitemap 項目"
    return doc


def read_sitemaps(seed, robots, in_scope, fetch, limit, *, max_files=MAX_FILES, document_origin=""):
    result = SitemapResult()
    candidates = sitemap_candidates(seed, robots)
    queue = deque((url, source, 0) for url, source in candidates.items())
    scheduled = {url for url, source in candidates.items() if source != "conventional"}
    seen_pages = set()
    found_root = False
    roots_read = children_read = 0
    while queue:
        url, source, depth = queue.popleft()
        if url in result.sources or (source == "conventional" and found_root):
            continue
        if not in_scope(url):
            result.pending[url] = "來源網域未確認或超出掃描範圍"
            continue
        if depth > 2 or (children_read if depth else roots_read) >= max_files:
            result.pending[url] = "超過子索引深度或 sitemap 檔案數上限"
            continue
        if depth:
            children_read += 1
        else:
            roots_read += 1
        result.sources[url] = source
        received = fetch(url)
        result.statuses[url] = received.status
        if received.limited:
            result.pending[url] = received.error
            continue
        if received.body is None:
            if source != "conventional" or received.error or received.status not in {404, 410}:
                result.errors[url] = received.error or f"HTTP {received.status}"
            continue
        result.documents[url] = received.body
        base = received.final_url or urljoin(document_origin, url)
        result.document_bases[url] = base
        doc = parse_sitemap(received.body, base)
        if doc.relative_links:
            result.relative_feeds.append(url)
        if not doc.kind:
            continue
        found_root |= bool(doc.urls) or not doc.problem
        for target in doc.urls:
            parsed = urlparse(target)
            target = parsed._replace(
                netloc=parsed.netloc.lower(), path=parsed.path or "/", fragment=""
            ).geturl()
            if doc.kind == "index":
                if target not in scheduled:
                    scheduled.add(target)
                    queue.append((target, url, depth + 1))
            elif in_scope(target) and target not in seen_pages:
                if len(result.records) >= limit:
                    result.pending[url] = f"超過本次網址上限 {limit}，尚有網址待爬"
                    break
                seen_pages.add(target)
                result.records.append(
                    UrlRecord(url=target, source="sitemap", discovered_depth=depth)
                )
    return result
