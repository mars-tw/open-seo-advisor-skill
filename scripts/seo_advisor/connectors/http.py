"""HTTPConnector：純公開 HTTP 爬取，唯讀，任何網站都可用，不需帳密。"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx

from seo_advisor.connectors.base import WebsiteConnector
from seo_advisor.models import ConnectorProfile, PageSnapshot, UrlRecord

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


class HTTPConnector(WebsiteConnector):
    """透過一般 HTTP 請求存取公開網站，僅發送 GET/HEAD，不需要任何憑證。"""

    def __init__(
        self,
        base_url: str,
        *,
        user_agent: str = "OpenSEOAdvisor/0.1",
        timeout_seconds: float = 15.0,
        max_redirects: int = 10,
    ) -> None:
        parsed = urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"base_url 必須是完整網址，收到：{base_url!r}")
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout_seconds,
            follow_redirects=True,
            max_redirects=max_redirects,
        )

    def id(self) -> str:
        return f"http:{urlparse(self.base_url).netloc}"

    def capabilities(self) -> set[str]:
        return {"read_urls"}

    def probe(self) -> ConnectorProfile:
        notes: list[str] = []
        has_robots = False
        has_sitemap = False
        detected_stack: str | None = None

        try:
            robots_resp = self._client.get(urljoin(self.base_url, "/robots.txt"))
            has_robots = robots_resp.status_code == 200
        except httpx.HTTPError as exc:
            notes.append(f"robots.txt 檢查失敗：{exc}")

        try:
            sitemap_resp = self._client.get(urljoin(self.base_url, "/sitemap.xml"))
            has_sitemap = sitemap_resp.status_code == 200
        except httpx.HTTPError as exc:
            notes.append(f"sitemap.xml 檢查失敗：{exc}")

        try:
            home_resp = self._client.get(self.base_url)
            server_header = home_resp.headers.get("server", "")
            powered_by = home_resp.headers.get("x-powered-by", "")
            body_snippet = home_resp.text[:5000].lower()
            if "wp-content" in body_snippet or "wordpress" in powered_by.lower():
                detected_stack = "wordpress"
            elif "shopify" in body_snippet:
                detected_stack = "shopify"
            elif "__next" in body_snippet:
                detected_stack = "nextjs"
            elif server_header:
                detected_stack = None
        except httpx.HTTPError as exc:
            notes.append(f"首頁請求失敗：{exc}")

        return ConnectorProfile(
            source_type="http",
            detected_stack=detected_stack,
            has_sitemap=has_sitemap,
            has_robots_txt=has_robots,
            notes=notes,
        )

    def list_urls(self, seed: str, limit: int) -> list[UrlRecord]:
        records: list[UrlRecord] = []
        sitemap_url = urljoin(self.base_url, "/sitemap.xml")
        try:
            resp = self._client.get(sitemap_url)
            if resp.status_code == 200:
                records.extend(self._parse_sitemap(resp.text, depth=0))
        except httpx.HTTPError:
            pass

        if not records:
            records.append(UrlRecord(url=seed or self.base_url, source="seed", discovered_depth=0))

        return records[:limit]

    def _parse_sitemap(self, xml_text: str, depth: int) -> list[UrlRecord]:
        records: list[UrlRecord] = []
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            return records

        tag = root.tag.lower()
        if tag.endswith("sitemapindex"):
            for sitemap_el in root.findall("sm:sitemap", _SITEMAP_NS):
                loc_el = sitemap_el.find("sm:loc", _SITEMAP_NS)
                if loc_el is not None and loc_el.text and depth < 2:
                    try:
                        child_resp = self._client.get(loc_el.text.strip())
                        if child_resp.status_code == 200:
                            records.extend(self._parse_sitemap(child_resp.text, depth + 1))
                    except httpx.HTTPError:
                        continue
        elif tag.endswith("urlset"):
            for url_el in root.findall("sm:url", _SITEMAP_NS):
                loc_el = url_el.find("sm:loc", _SITEMAP_NS)
                if loc_el is not None and loc_el.text:
                    records.append(
                        UrlRecord(url=loc_el.text.strip(), source="sitemap", discovered_depth=depth)
                    )
        return records

    def fetch_url(self, url: str, render: bool = False, fetched_at: str = "") -> PageSnapshot:
        if render:
            raise NotImplementedError(
                "render=True 需要 Playwright 支援，v0.1.0 尚未實作，見 docs/roadmap.md。"
            )

        redirect_chain: list[str] = []
        try:
            resp = self._client.get(url)
            for history_resp in resp.history:
                redirect_chain.append(str(history_resp.url))
            return PageSnapshot(
                url=url,
                status_code=resp.status_code,
                final_url=str(resp.url),
                redirect_chain=redirect_chain,
                headers=dict(resp.headers),
                html=resp.text if "text/html" in resp.headers.get("content-type", "") else "",
                fetched_at=fetched_at,
            )
        except httpx.HTTPError:
            return PageSnapshot(
                url=url,
                status_code=0,
                final_url=url,
                redirect_chain=redirect_chain,
                headers={},
                html="",
                fetched_at=fetched_at,
            )

    def close(self) -> None:
        self._client.close()
