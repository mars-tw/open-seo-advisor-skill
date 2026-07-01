"""技術面爬蟲：透過 WebsiteConnector 收集頁面快照與站台層級資訊。

crawler 本身不判斷「好不好」，只負責收集事實（狀態碼、HTML、連結、
robots.txt/sitemap 內容）。判斷邏輯在 analyzers/ 中實作，這樣可以讓
crawler 被所有分析模組共用。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from seo_advisor.connectors.base import WebsiteConnector
from seo_advisor.models import PageSnapshot


@dataclass
class CrawlResult:
    pages: dict[str, PageSnapshot] = field(default_factory=dict)
    robots_txt: str | None = None
    sitemap_xml: str | None = None
    link_graph: dict[str, set[str]] = field(default_factory=dict)
    skipped_urls: list[str] = field(default_factory=list)


def _same_site(base_netloc: str, url: str) -> bool:
    return urlparse(url).netloc in ("", base_netloc)


def _extract_links(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        links.append(urljoin(base_url, href))
    return links


def crawl_site(
    connector: WebsiteConnector,
    *,
    seed_url: str,
    max_urls: int = 1000,
    max_depth: int = 6,
    fetched_at: str = "",
) -> CrawlResult:
    """從 seed_url 開始做站內廣度優先爬取，回傳收集到的所有頁面快照。"""

    result = CrawlResult()
    base_netloc = urlparse(seed_url).netloc

    try:
        robots_snapshot = connector.fetch_url(
            urljoin(seed_url, "/robots.txt"), fetched_at=fetched_at
        )
        if robots_snapshot.status_code == 200:
            result.robots_txt = robots_snapshot.html or robots_snapshot.headers.get("_raw_text", "")
    except Exception:
        pass

    try:
        sitemap_snapshot = connector.fetch_url(
            urljoin(seed_url, "/sitemap.xml"), fetched_at=fetched_at
        )
        if sitemap_snapshot.status_code == 200:
            result.sitemap_xml = sitemap_snapshot.html
    except Exception:
        pass

    seed_records = connector.list_urls(seed_url, limit=max_urls)
    queue: deque[tuple[str, int]] = deque((r.url, r.discovered_depth) for r in seed_records)
    if not queue:
        queue.append((seed_url, 0))

    visited: set[str] = set()

    while queue and len(result.pages) < max_urls:
        url, depth = queue.popleft()
        if url in visited or depth > max_depth:
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
            same_site_links = [link for link in links if _same_site(base_netloc, link)]
            result.link_graph[url] = set(same_site_links)
            for link in same_site_links:
                if link not in visited:
                    queue.append((link, depth + 1))
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
    for targets in result.link_graph.values():
        linked_targets.update(targets)

    entry_points = {seed_url} if seed_url in result.pages else set()
    if not entry_points:
        entry_points = {
            url
            for url in result.pages
            if url not in linked_targets and result.link_graph.get(url)
        }

    orphans = [
        url
        for url in result.pages
        if url not in entry_points and url not in linked_targets
    ]
    return orphans
