"""HTTPConnector：純公開 HTTP 爬取，唯讀，任何網站都可用，不需帳密。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx

from seo_advisor.connectors.base import WebsiteConnector
from seo_advisor.models import ConnectorProfile, PageSnapshot, SafetyPolicy, UrlRecord
from seo_advisor.security.network_policy import PrivateNetworkBlockedError, ensure_host_allowed
from seo_advisor.security.rate_limiter import RateLimiter
from seo_advisor.security.robots_policy import RobotsPolicy

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

# 回應大小上限：避免惡意或異常的巨大回應吃爆記憶體。HTML 頁面正常遠小於此。
_MAX_HTML_BYTES = 10 * 1024 * 1024  # 10 MB
_MAX_SITEMAP_BYTES = 20 * 1024 * 1024  # 20 MB（sitemap 可能較大但仍需上限）
_MAX_SITEMAP_FILES = 50  # sitemap index 最多追蹤的子 sitemap 數，避免請求放大


@dataclass
class _SafeResponse:
    """_safe_get 的結果：body 已在串流時受大小上限保護、與 response 生命週期解耦。"""

    status_code: int
    final_url: str
    headers: dict[str, str]
    body: bytes
    encoding: str
    history: list[str]
    truncated: bool = False


def _decode_body(resp: _SafeResponse) -> str:
    """把已受大小上限保護的 body 解碼成文字（header 說謊也已在下載時被截斷）。"""
    try:
        return resp.body.decode(resp.encoding, errors="replace")
    except (LookupError, ValueError):
        return resp.body.decode("utf-8", errors="replace")


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
        self._max_redirects = max_redirects

        # follow_redirects=False：改由 _safe_get 手動追 redirect，每一跳都重新做
        # SSRF 檢查（ensure_host_allowed）。否則 httpx 自動跟隨 redirect 時，公開
        # 網址可被 30x 導向 private IP 或雲端 metadata endpoint 繞過原本的檢查。
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout_seconds,
            follow_redirects=False,
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

    def _safe_get(self, url: str, *, max_bytes: int = _MAX_HTML_BYTES) -> _SafeResponse:
        """發送 GET 並手動跟隨 redirect，每一跳都重新做 SSRF 檢查，且串流讀取
        body 並在超過 max_bytes 時中止，避免超大回應把整個 body 讀進記憶體。

        每一跳都會：
        - 只允許 http/https scheme（擋掉 file://、ftp:// 等）
        - 呼叫 ensure_host_allowed（擋 private/loopback/metadata IP）
        - 超過 max_redirects 即停止並拋出 httpx.HTTPError
        """
        history: list[str] = []
        current = url
        for _ in range(self._max_redirects + 1):
            parsed = urlparse(current)
            if parsed.scheme not in ("http", "https"):
                raise httpx.RequestError(f"不允許的 redirect scheme：{parsed.scheme!r}")
            ensure_host_allowed(current, allow_private_network=self.policy.allow_private_network)

            with self._client.stream("GET", current) as resp:
                if resp.is_redirect and resp.headers.get("location"):
                    history.append(str(resp.url))
                    # redirect 只需 headers，body 不讀；用當前 URL 解析相對 Location
                    current = urljoin(current, resp.headers["location"])
                    continue

                # 串流累加 body，一旦超過上限就中止下載，避免記憶體被撐爆。
                declared = resp.headers.get("content-length")
                if declared and declared.isdigit() and int(declared) > max_bytes:
                    body = b""
                    truncated = True
                else:
                    chunks: list[bytes] = []
                    total = 0
                    truncated = False
                    for chunk in resp.iter_bytes():
                        chunks.append(chunk)
                        total += len(chunk)
                        if total > max_bytes:
                            truncated = True
                            break
                    body = b"".join(chunks)[:max_bytes] if not truncated else b""
                return _SafeResponse(
                    status_code=resp.status_code,
                    final_url=str(resp.url),
                    headers=dict(resp.headers),
                    body=body,
                    encoding=resp.encoding or "utf-8",
                    history=history,
                    truncated=truncated,
                )
        raise httpx.RequestError(f"redirect 次數超過上限（{self._max_redirects}）：{url}")

    def probe(self) -> ConnectorProfile:
        notes: list[str] = []
        has_robots = False
        has_sitemap = False
        detected_stack: str | None = None

        try:
            robots_resp = self._safe_get(urljoin(self.base_url, "/robots.txt"))
            has_robots = robots_resp.status_code == 200
            if self.policy.respect_robots_txt:
                self._robots_policy = RobotsPolicy(
                    _decode_body(robots_resp) if has_robots else None,
                    user_agent=self._user_agent,
                )
                if not has_robots:
                    notes.append("網站沒有 robots.txt，預設允許爬取所有頁面。")
        except (httpx.HTTPError, PrivateNetworkBlockedError) as exc:
            notes.append(f"robots.txt 檢查失敗：{exc}")

        try:
            sitemap_resp = self._safe_get(urljoin(self.base_url, "/sitemap.xml"))
            has_sitemap = sitemap_resp.status_code == 200
        except (httpx.HTTPError, PrivateNetworkBlockedError) as exc:
            notes.append(f"sitemap.xml 檢查失敗：{exc}")

        try:
            home_resp = self._safe_get(self.base_url)
            server_header = home_resp.headers.get("server", "")
            powered_by = home_resp.headers.get("x-powered-by", "")
            body_snippet = _decode_body(home_resp)[:5000].lower()
            if "wp-content" in body_snippet or "wordpress" in powered_by.lower():
                detected_stack = "wordpress"
            elif "shopify" in body_snippet:
                detected_stack = "shopify"
            elif "__next" in body_snippet:
                detected_stack = "nextjs"
            elif server_header:
                detected_stack = None
        except (httpx.HTTPError, PrivateNetworkBlockedError) as exc:
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
            resp = self._safe_get(sitemap_url, max_bytes=_MAX_SITEMAP_BYTES)
            if resp.status_code == 200:
                records.extend(
                    self._parse_sitemap(
                        _decode_body(resp),
                        depth=0,
                        limit=limit,
                        skipped_external=skipped_external,
                    )
                )
        except (httpx.HTTPError, PrivateNetworkBlockedError):
            pass

        if not records:
            records.append(UrlRecord(url=seed or self.base_url, source="seed", discovered_depth=0))

        return records[:limit]

    def _parse_sitemap(
        self, xml_text: str, depth: int, *, limit: int, skipped_external: list[str]
    ) -> list[UrlRecord]:
        records: list[UrlRecord] = []
        # XML 安全：正常 sitemap 不需要 DTD 或自訂 entity；直接拒絕含 DOCTYPE/
        # ENTITY 的內容，徹底避免 entity expansion（billion laughs）與 XXE。
        # 另外 body 已在下載時經 _MAX_SITEMAP_BYTES 上限保護。
        head = xml_text[:2048].lower()
        if "<!doctype" in head or "<!entity" in head:
            return records
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            return records

        tag = root.tag.lower()
        if tag.endswith("sitemapindex"):
            child_count = 0
            for sitemap_el in root.findall("sm:sitemap", _SITEMAP_NS):
                # 已蒐集到足夠 URL，或子 sitemap 數超過上限就停，避免 sitemap
                # index 觸發大量請求（DoS 放大 / 資源耗盡）。
                if len(records) >= limit or child_count >= _MAX_SITEMAP_FILES:
                    break
                loc_el = sitemap_el.find("sm:loc", _SITEMAP_NS)
                if loc_el is None or not loc_el.text or depth >= 2:
                    continue
                child_url = loc_el.text.strip()
                if not self.is_url_in_scope(child_url):
                    skipped_external.append(child_url)
                    continue
                child_count += 1
                try:
                    # 每次抓子 sitemap 前套 rate limit，避免對目標站發太多請求
                    self._rate_limiter.wait()
                    child_resp = self._safe_get(child_url, max_bytes=_MAX_SITEMAP_BYTES)
                    if child_resp.status_code == 200:
                        records.extend(
                            self._parse_sitemap(
                                _decode_body(child_resp),
                                depth + 1,
                                limit=limit,
                                skipped_external=skipped_external,
                            )
                        )
                except (httpx.HTTPError, PrivateNetworkBlockedError):
                    continue
        elif tag.endswith("urlset"):
            for url_el in root.findall("sm:url", _SITEMAP_NS):
                if len(records) >= limit:
                    break
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
            resp = self._safe_get(url)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            self._register_final_host(resp.final_url)
            is_html = "text/html" in resp.headers.get("content-type", "")
            return PageSnapshot(
                url=url,
                status_code=resp.status_code,
                final_url=resp.final_url,
                redirect_chain=resp.history,
                headers=resp.headers,
                html=_decode_body(resp) if is_html else "",
                fetched_at=fetched_at,
                elapsed_ms=elapsed_ms,
            )
        except PrivateNetworkBlockedError as exc:
            # redirect 中途被導向私有網段/metadata：擋下並如實回報
            return PageSnapshot(
                url=url,
                status_code=0,
                final_url=url,
                redirect_chain=redirect_chain,
                headers={},
                html="",
                fetched_at=fetched_at,
                fetch_error_type="private_network_blocked",
                fetch_error_message=str(exc),
                elapsed_ms=int((time.monotonic() - start) * 1000),
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
