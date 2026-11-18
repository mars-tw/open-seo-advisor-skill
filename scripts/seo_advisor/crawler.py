"""技術面爬蟲：透過 WebsiteConnector 收集頁面快照與站台層級資訊。

crawler 本身不判斷「好不好」，只負責收集事實（狀態碼、HTML、連結、
robots.txt/sitemap 內容）。判斷邏輯在 analyzers/ 中實作，這樣可以讓
crawler 被所有分析模組共用。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

from seo_advisor.connectors.base import WebsiteConnector
from seo_advisor.models import PageSnapshot
from seo_advisor.sitemaps import MAX_FILES, SitemapFetch, read_sitemaps
from seo_advisor.url_utils import normalize_host


@dataclass
class CrawlResult:
    pages: dict[str, PageSnapshot] = field(default_factory=dict)
    robots_txt: str | None = None
    sitemap_xml: str | None = None
    link_graph: dict[str, set[str]] = field(default_factory=dict)
    skipped_urls: list[str] = field(default_factory=list)
    sitemap_documents: dict[str, str] = field(default_factory=dict)
    sitemap_sources: dict[str, str] = field(default_factory=dict)
    sitemap_page_urls: set[str] = field(default_factory=set)
    sitemap_statuses: dict[str, int] = field(default_factory=dict)
    sitemap_errors: dict[str, str] = field(default_factory=dict)
    sitemap_pending: dict[str, str] = field(default_factory=dict)
    unverified_canonicals: dict[str, str] = field(default_factory=dict)


def _same_site(base_netloc: str, url: str) -> bool:
    """判斷 url 是否與 base_netloc 同站；www.example.com 與 example.com
    視為同站，避免漏爬網站的 www/apex 兩個版本（見 HTTPConnector.is_url_in_scope
    的同一套正規化邏輯，兩者共用 url_utils.normalize_host）。"""
    netloc = urlparse(url).netloc
    return netloc == "" or normalize_host(netloc) == normalize_host(base_netloc)


def _document_url(url: str, base_url: str = "") -> str:
    """Resolve a document URL without its fragment; keep path/query data intact."""
    document = urldefrag(urljoin(base_url, url)).url
    parsed = urlparse(document)
    # HTTP's empty root path and '/' request the same document. Local paths stay unchanged.
    if parsed.scheme in ("http", "https") and parsed.netloc and not parsed.path:
        document = parsed._replace(path="/").geturl()
    return document


def document_base(base_url: str, soup: BeautifulSoup) -> str:
    for base_tag in soup.find_all("base", href=True):
        try:
            candidate = urljoin(base_url, base_tag["href"].strip())
        except ValueError:
            continue
        if urlparse(candidate).scheme in {"", "http", "https"}:
            return candidate
    return base_url


def _extract_links(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    effective_base = document_base(base_url, soup)
    links: list[str] = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or (href.startswith("#") and effective_base == base_url):
            continue
        try:
            target = _document_url(href, effective_base)
            if urlparse(target).scheme in {"", "http", "https"}:
                links.append(target)
        except ValueError:
            continue
    return links


def crawl_site(
    connector: WebsiteConnector,
    *,
    seed_url: str,
    max_urls: int = 1000,
    max_depth: int = 6,
    max_sitemap_files: int = MAX_FILES,
    fetched_at: str = "",
) -> CrawlResult:
    """從 seed_url 開始做站內廣度優先爬取，回傳收集到的所有頁面快照。"""

    seed_url = _document_url(seed_url)
    result = CrawlResult()
    base_netloc = urlparse(seed_url).netloc
    is_in_scope = getattr(connector, "is_url_in_scope", None)

    try:
        robots_snapshot = connector.fetch_url(
            urljoin(seed_url, "/robots.txt"), fetched_at=fetched_at
        )
        if robots_snapshot.status_code == 200:
            result.robots_txt = (
                robots_snapshot.text if robots_snapshot.text is not None else robots_snapshot.html
            )
    except Exception:
        pass

    def fetch_sitemap(url):
        try:
            snapshot = connector.fetch_url(url, fetched_at=fetched_at)
        except (OSError, ValueError) as exc:
            return SitemapFetch(0, error=type(exc).__name__)
        body = snapshot.text if snapshot.text is not None else snapshot.html
        if snapshot.status_code == 200 and isinstance(body, str):
            return SitemapFetch(200, body)
        return SitemapFetch(snapshot.status_code, error=snapshot.fetch_error_type or "")

    reader = getattr(type(connector), "read_sitemap_file", None)
    sitemap_data = read_sitemaps(
        seed_url,
        result.robots_txt,
        is_in_scope or (lambda url: _same_site(base_netloc, url)),
        connector.read_sitemap_file if callable(reader) else fetch_sitemap,
        max_urls,
        max_files=max_sitemap_files,
    )
    result.sitemap_page_urls = {record.url for record in sitemap_data.records}
    result.sitemap_sources = sitemap_data.sources
    result.sitemap_documents = sitemap_data.documents
    result.sitemap_statuses = sitemap_data.statuses
    result.sitemap_errors = sitemap_data.errors
    result.sitemap_pending = sitemap_data.pending
    result.sitemap_xml = next(iter(sitemap_data.documents.values()), None)
    http_reader = callable(getattr(type(connector), "read_sitemap", None))
    seed_records = (
        sitemap_data.records if http_reader else connector.list_urls(seed_url, limit=max_urls)
    )
    local_url = getattr(type(connector), "local_url", None)
    if callable(local_url) and getattr(connector, "site_origin", None):
        seed_records.extend(
            record.model_copy(update={"url": connector.local_url(record.url)})
            for record in sitemap_data.records
        )
    queue: deque[tuple[str, int]] = deque()
    queued_depths: dict[str, int] = {}
    visited: set[str] = set()

    def enqueue(url: str, depth: int) -> None:
        url = _document_url(url, seed_url)
        if callable(local_url):
            url = connector.local_url(url)
        if url in visited or (url in queued_depths and queued_depths[url] <= depth):
            return
        queued_depths[url] = depth
        queue.append((url, depth))

    if http_reader:
        enqueue(seed_url, 0)
    for record in seed_records:
        enqueue(record.url, record.discovered_depth)
    if not queue:
        enqueue(seed_url, 0)

    while queue and len(result.pages) < max_urls:
        url, depth = queue.popleft()
        if url in visited or depth > max_depth or queued_depths[url] != depth:
            continue
        visited.add(url)

        try:
            snapshot = connector.fetch_url(url, fetched_at=fetched_at)
        except Exception:
            result.skipped_urls.append(url)
            continue

        result.pages[url] = snapshot

        if snapshot.html and depth < max_depth:
            links = _extract_links(snapshot.final_url or url, snapshot.html)
            if is_in_scope is not None:
                same_site_links = [link for link in links if is_in_scope(link)]
            else:
                same_site_links = [link for link in links if _same_site(base_netloc, link)]
            if callable(local_url):
                same_site_links = [connector.local_url(link) for link in same_site_links]
            result.link_graph[url] = set(same_site_links)
            for link in same_site_links:
                enqueue(link, depth + 1)
        else:
            result.link_graph.setdefault(url, set())

    return result


def find_orphan_pages(result: CrawlResult, seed_url: str) -> list[str]:
    """找出沒有被任何其他頁面連結到的頁面（入口頁除外）。

    若網站只有單一頁面，沒有「被連結」的意義，一律不視為孤兒頁。
    入口頁的判定：優先用 seed_url 本身；若 seed_url 未實際出現在
    爬取結果中（例如本地原始碼包用路徑列舉而非單一入口爬取），
    則退而以「沒有其他頁面連到它，但它有連到其他頁面」的頁面視為入口候選，
    不列入孤兒頁清單。
    """
    if len(result.pages) <= 1:
        return []

    linked_targets: set[str] = set()
    for source, targets in result.link_graph.items():
        linked_targets.update(
            target for target in targets if _document_url(target) != _document_url(source)
        )

    seed_url = _document_url(seed_url)
    entry_points = {seed_url} if seed_url in result.pages else set()
    if not entry_points:
        entry_points = {
            url
            for url in result.pages
            if url not in linked_targets
            and any(target != url for target in result.link_graph.get(url, ()))
        }

    orphans = [
        url
        for url, snapshot in result.pages.items()
        if snapshot.status_code == 200
        and snapshot.html
        and not snapshot.fetch_error_type
        and url not in entry_points
        and url not in linked_targets
    ]
    return orphans
