"""HTTPConnector：純公開 HTTP 爬取，唯讀，任何網站都可用，不需帳密。"""

from __future__ import annotations

import time
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx

from seo_advisor.connectors.base import WebsiteConnector
from seo_advisor.models import ConnectorProfile, PageSnapshot, SafetyPolicy, UrlRecord
from seo_advisor.security.network_policy import PrivateNetworkBlockedError, ensure_host_allowed
from seo_advisor.security.rate_limiter import RateLimiter
from seo_advisor.security.robots_policy import RobotsPolicy

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
        policy: SafetyPolicy | None = None,
    ) -> None:
        self.policy = policy or SafetyPolicy(allowed_capabilities={"read_urls"})
        self._user_agent = user_agent

        parsed = urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"base_url 必須是完整網址，收到：{base_url!r}")
        ensure_host_allowed(base_url, allow_private_network=self.policy.allow_private_network)

        self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        # 允許存取的 host 別名集合：初始只有 seed 的 host，之後若第一次請求
        # 發生 redirect（例如 example.com -> www.example.com），會把新 host
        # 加入這個集合，避免爬蟲把「正確的最終網域」誤判為外部連結而漏爬。
        self._allowed_netlocs: set[str] = {parsed.netloc}
        self._rate_limiter = RateLimiter(self.policy.rate_limit_per_second)
        self._robots_policy: RobotsPolicy | None = None

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

    def is_url_in_scope(self, url: str) -> bool:
        """判斷 URL 的 host 是否在允許爬取的範圍內（seed host 或其 redirect 目標）。"""
        netloc = urlparse(url).netloc
        return netloc in ("", *self._allowed_netlocs)

    def _register_final_host(self, final_url: str) -> None:
        netloc = urlparse(final_url).netloc
        if netloc:
            self._allowed_netlocs.add(netloc)

    def probe(self) -> ConnectorProfile:
        notes: list[str] = []
        has_robots = False
        has_sitemap = False
        detected_stack: str | None = None

        try:
            robots_resp = self._client.get(urljoin(self.base_url, "/robots.txt"))
            has_robots = robots_resp.status_code == 200
            if self.policy.respect_robots_txt:
                self._robots_policy = RobotsPolicy(
                    robots_resp.text if has_robots else None, user_agent=self._user_agent
                )
                if not has_robots:
                    notes.append("網站沒有 robots.txt，預設允許爬取所有頁面。")
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
        skipped_external: list[str] = []
        sitemap_url = urljoin(self.base_url, "/sitemap.xml")
        try:
            resp = self._client.get(sitemap_url)
            if resp.status_code == 200:
                records.extend(self._parse_sitemap(resp.text, depth=0, skipped_external=skipped_external))
        except httpx.HTTPError:
            pass

        if not records:
            records.append(UrlRecord(url=seed or self.base_url, source="seed", discovered_depth=0))

        return records[:limit]

    def _parse_sitemap(
        self, xml_text: str, depth: int, *, skipped_external: list[str]
    ) -> list[UrlRecord]:
        records: list[UrlRecord] = []
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            return records

        tag = root.tag.lower()
        if tag.endswith("sitemapindex"):
            for sitemap_el in root.findall("sm:sitemap", _SITEMAP_NS):
                loc_el = sitemap_el.find("sm:loc", _SITEMAP_NS)
                if loc_el is None or not loc_el.text or depth >= 2:
                    continue
                child_url = loc_el.text.strip()
                if not self.is_url_in_scope(child_url):
                    skipped_external.append(child_url)
                    continue
                try:
                    child_resp = self._client.get(child_url)
                    if child_resp.status_code == 200:
                        records.extend(
                            self._parse_sitemap(
                                child_resp.text, depth + 1, skipped_external=skipped_external
                            )
                        )
                except httpx.HTTPError:
                    continue
        elif tag.endswith("urlset"):
            for url_el in root.findall("sm:url", _SITEMAP_NS):
                loc_el = url_el.find("sm:loc", _SITEMAP_NS)
                if loc_el is None or not loc_el.text:
                    continue
                page_url = loc_el.text.strip()
                if not self.is_url_in_scope(page_url):
                    skipped_external.append(page_url)
                    continue
                records.append(
                    UrlRecord(url=page_url, source="sitemap", discovered_depth=depth)
                )
        return records

    def fetch_url(self, url: str, *, render: bool = False, fetched_at: str = "") -> PageSnapshot:
        if render:
            raise NotImplementedError(
                "render=True 需要 Playwright 支援，v0.1.0 尚未實作，見 docs/roadmap.md。"
            )

        try:
            ensure_host_allowed(url, allow_private_network=self.policy.allow_private_network)
        except PrivateNetworkBlockedError as exc:
            return PageSnapshot(
                url=url,
                status_code=0,
                final_url=url,
                headers={},
                html="",
                fetched_at=fetched_at,
                fetch_error_type="private_network_blocked",
                fetch_error_message=str(exc),
            )

        if self._robots_policy is not None and not self._robots_policy.is_allowed(url):
            return PageSnapshot(
                url=url,
                status_code=0,
                final_url=url,
                headers={},
                html="",
                fetched_at=fetched_at,
                fetch_error_type="blocked_by_robots_txt",
                fetch_error_message=f"robots.txt 不允許爬取此 URL：{url}",
            )

        self._rate_limiter.wait()

        redirect_chain: list[str] = []
        start = time.monotonic()
        try:
            resp = self._client.get(url)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            for history_resp in resp.history:
                redirect_chain.append(str(history_resp.url))
            self._register_final_host(str(resp.url))
            return PageSnapshot(
                url=url,
                status_code=resp.status_code,
                final_url=str(resp.url),
                redirect_chain=redirect_chain,
                headers=dict(resp.headers),
                html=resp.text if "text/html" in resp.headers.get("content-type", "") else "",
                fetched_at=fetched_at,
                elapsed_ms=elapsed_ms,
            )
        except httpx.TimeoutException as exc:
            return PageSnapshot(
                url=url,
                status_code=0,
                final_url=url,
                redirect_chain=redirect_chain,
                headers={},
                html="",
                fetched_at=fetched_at,
                fetch_error_type="timeout",
                fetch_error_message=str(exc),
                elapsed_ms=int((time.monotonic() - start) * 1000),
            )
        except httpx.ConnectError as exc:
            return PageSnapshot(
                url=url,
                status_code=0,
                final_url=url,
                redirect_chain=redirect_chain,
                headers={},
                html="",
                fetched_at=fetched_at,
                fetch_error_type="connect_error",
                fetch_error_message=str(exc),
                elapsed_ms=int((time.monotonic() - start) * 1000),
            )
        except httpx.HTTPError as exc:
            return PageSnapshot(
                url=url,
                status_code=0,
                final_url=url,
                redirect_chain=redirect_chain,
                headers={},
                html="",
                fetched_at=fetched_at,
                fetch_error_type=type(exc).__name__,
                fetch_error_message=str(exc),
                elapsed_ms=int((time.monotonic() - start) * 1000),
            )

    def close(self) -> None:
        self._client.close()
