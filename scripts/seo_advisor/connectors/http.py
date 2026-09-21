"""HTTPConnector：純公開 HTTP 爬取，唯讀，任何網站都可用，不需帳密。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx

from seo_advisor.connectors.base import WebsiteConnector
from seo_advisor.models import ConnectorProfile, PageSnapshot, ProbeResult, SafetyPolicy, UrlRecord
from seo_advisor.security.network_policy import PrivateNetworkBlockedError, ensure_host_allowed
from seo_advisor.security.rate_limiter import RateLimiter
from seo_advisor.security.robots_policy import RobotsPolicy
from seo_advisor.url_utils import normalize_host

# probe_path() 讀取內容的上限：只需要極少量內容判斷特徵（例如 ".env" 檔案開頭
# 幾行是否像環境變數格式），完全不需要下載整個檔案。
_MAX_PROBE_BYTES = 4096
_PROBE_PREVIEW_CHARS = 200

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

# 回應大小上限：避免惡意或異常的巨大回應吃爆記憶體。HTML 頁面正常遠小於此。
_MAX_HTML_BYTES = 10 * 1024 * 1024  # 10 MB
_MAX_SITEMAP_BYTES = 20 * 1024 * 1024  # 20 MB（sitemap 可能較大但仍需上限）
_MAX_SITEMAP_FILES = 50  # sitemap index 最多追蹤的子 sitemap 數，避免請求放大

# extra_headers 建構子參數只允許這些不涉及認證/身分的 header，避免這個
# 參數被誤用成通用的任意 header 注入口（例如塞入 Authorization/Cookie
# 讓 HTTPConnector 變成可以代打認證請求的工具，遠超出「唯讀公開爬取」的
# 定位）。目前唯一的使用場景是 Security Mode 的 referrer-based redirect
# 檢查（見 security_mode/cloaking.py），只需要 Referer。
_ALLOWED_EXTRA_HEADER_NAMES = frozenset({"referer", "accept-language"})


class DisallowedExtraHeaderError(ValueError):
    """extra_headers 包含不在允許清單內的 header 名稱時拋出。"""


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


def _is_textual_content_type(content_type: str) -> bool:
    """判斷這個 content-type 是否為「文字類」，決定要不要把 decode 後的 body
    保留到 PageSnapshot.html。

    保留：HTML、XML（含 sitemap 的 application/xml、text/xml、任何 +xml）、
    純文字（robots.txt 的 text/plain）、JSON、JavaScript/CSS 等文字資源。
    不保留：圖片、字型、PDF、壓縮檔等二進位內容——這些塞進 html 欄位只會產生
    亂碼，且下游分析器（HTML 解析、XML 解析）都以文字為前提。

    修正紀錄：早期只用 `"text/html" in content-type` 判斷，導致 sitemap.xml
    （application/xml）與 robots.txt（text/plain）的 body 被丟成空字串，
    連帶讓 sitemap 分析器對空字串呼叫 ElementTree.fromstring 而誤報「非合法 XML」。
    """
    ct = content_type.split(";", 1)[0].strip().lower()
    if not ct:
        # 沒宣告 content-type：保守地不當作文字，維持與舊行為一致（避免把
        # 無 header 的二進位回應也 decode 進 html）。
        return False
    if ct.startswith("text/"):
        return True
    if ct.endswith("+xml") or ct.endswith("+json"):
        # application/rss+xml、application/atom+xml、image/svg+xml、
        # application/ld+json 等都由這裡涵蓋。
        return True
    return ct in {
        "application/xml",
        "application/json",
        "application/javascript",
    }


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
        rate_limiter: RateLimiter | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.policy = policy or SafetyPolicy(allowed_capabilities={"read_urls"})
        self._user_agent = user_agent

        if extra_headers:
            for name in extra_headers:
                if name.lower() not in _ALLOWED_EXTRA_HEADER_NAMES:
                    raise DisallowedExtraHeaderError(
                        f"extra_headers 不允許 {name!r}，只允許 "
                        f"{sorted(_ALLOWED_EXTRA_HEADER_NAMES)}。HTTPConnector 是唯讀公開"
                        "爬取工具，不支援夾帶認證/身分類 header（Authorization/Cookie 等），"
                        "避免這個參數被誤用成任意 header 注入介面。"
                    )

        parsed = urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"base_url 必須是完整網址，收到：{base_url!r}")
        ensure_host_allowed(base_url, allow_private_network=self.policy.allow_private_network)

        self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        # 允許存取的 host 別名集合：初始只有 seed 的 host，之後若第一次請求
        # 發生 redirect（例如 example.com -> www.example.com），會把新 host
        # 加入這個集合，避免爬蟲把「正確的最終網域」誤判為外部連結而漏爬。
        self._allowed_netlocs: set[str] = {parsed.netloc}
        # rate_limiter 可由呼叫端注入共用實例：Security Mode 對同一個目標
        # 網站可能會建立多個 HTTPConnector（例如 cloaking 檢查切換 User-Agent
        # 需要獨立的 connector），若各自建立獨立的 RateLimiter，總請求速率會
        # 隨 connector 數量而倍增，等於讓「對目標網站友善」這個防護名存實亡。
        # 傳入同一個 RateLimiter 實例即可讓多個 connector 共享同一個節流時鐘。
        self._rate_limiter = rate_limiter or RateLimiter(self.policy.rate_limit_per_second)
        self._robots_policy: RobotsPolicy | None = None
        self._max_redirects = max_redirects
        # 單次掃描內，同一個 URL（robots.txt/sitemap.xml/首頁等）常被 probe()、
        # 前置檢查、crawl_site、list_urls() 各自呼叫一次；用小型記憶體快取避免
        # 對同一目標網站重複發送相同請求（省時間、也減少對被掃網站的負擔）。
        self._response_cache: dict[str, _SafeResponse] = {}

        # follow_redirects=False：改由 _safe_get 手動追 redirect，每一跳都重新做
        # SSRF 檢查（ensure_host_allowed）。否則 httpx 自動跟隨 redirect 時，公開
        # 網址可被 30x 導向 private IP 或雲端 metadata endpoint 繞過原本的檢查。
        #
        # extra_headers 目前只給 Security Mode 的 referrer-based redirect 檢查
        # 使用（固定的 Google 搜尋結果 Referer 字串，見 security_mode/cloaking.py），
        # 不是通用的任意 header 注入介面；一般爬取流程不會使用這個參數。
        headers = {"User-Agent": user_agent}
        if extra_headers:
            headers.update(extra_headers)
        self._client = httpx.Client(
            headers=headers,
            timeout=timeout_seconds,
            follow_redirects=False,
        )

    def id(self) -> str:
        return f"http:{urlparse(self.base_url).netloc}"

    def capabilities(self) -> set[str]:
        return {"read_urls"}

    def is_url_in_scope(self, url: str) -> bool:
        """判斷 URL 的 host 是否在允許爬取的範圍內（seed host、其 redirect 目標，
        或兩者的 www↔apex 版本）。

        正規化後比較：www.example.com 與 example.com 視為同站，避免網站的
        www/apex 兩個版本沒有互相 redirect 時，把同站頁面誤判為外部連結而漏爬。
        """
        netloc = urlparse(url).netloc
        if netloc == "":
            return True
        normalized = normalize_host(netloc)
        return any(normalized == normalize_host(allowed) for allowed in self._allowed_netlocs)

    def _register_final_host(self, final_url: str) -> None:
        netloc = urlparse(final_url).netloc
        if netloc:
            self._allowed_netlocs.add(netloc)

    def _safe_get(
        self,
        url: str,
        *,
        max_bytes: int = _MAX_HTML_BYTES,
        use_cache: bool = False,
        same_origin_only: bool = False,
    ) -> _SafeResponse:
        """發送 GET 並手動跟隨 redirect，每一跳都重新做 SSRF 檢查，且串流讀取
        body 並在超過 max_bytes 時中止，避免超大回應把整個 body 讀進記憶體。

        每一跳都會：
        - 只允許 http/https scheme（擋掉 file://、ftp:// 等）
        - 呼叫 ensure_host_allowed（擋 private/loopback/metadata IP）
        - 超過 max_redirects 即停止並拋出 httpx.HTTPError

        use_cache=True 時，同一個 url 在本 connector 生命週期內只會真正發送一次
        請求；只用於 probe()/list_urls() 這類明確會被多處重複呼叫的固定路徑
        （robots.txt/sitemap.xml/首頁），一般頁面爬取不套用，避免快取到過期內容。

        same_origin_only=True 時，一旦 redirect 目標的 host 與初始請求不同站
        （用 normalize_host 正規化後比較，www/apex 視為同站），立刻停止並回傳
        redirect 當下的回應（不追過去）。用於 Security Mode 對敏感路徑
        （如 /.env）探測時：使用者只授權掃描自己的網站，若該路徑意外 redirect
        到第三方網域，繼續追下去等於對未授權的第三方主機發送敏感路徑探測。
        """
        if use_cache and url in self._response_cache:
            return self._response_cache[url]

        origin_host = urlparse(url).netloc
        history: list[str] = []
        current = url
        for _ in range(self._max_redirects + 1):
            parsed = urlparse(current)
            if parsed.scheme not in ("http", "https"):
                raise httpx.RequestError(f"不允許的 redirect scheme：{parsed.scheme!r}")
            if same_origin_only and normalize_host(parsed.netloc) != normalize_host(origin_host):
                return _SafeResponse(
                    status_code=0,
                    final_url=current,
                    headers={},
                    body=b"",
                    encoding="utf-8",
                    history=history,
                    truncated=False,
                )
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
                result = _SafeResponse(
                    status_code=resp.status_code,
                    final_url=str(resp.url),
                    headers=dict(resp.headers),
                    body=body,
                    encoding=resp.encoding or "utf-8",
                    history=history,
                    truncated=truncated,
                )
                if use_cache:
                    self._response_cache[url] = result
                return result
        raise httpx.RequestError(f"redirect 次數超過上限（{self._max_redirects}）：{url}")

    def probe(self) -> ConnectorProfile:
        notes: list[str] = []
        has_robots = False
        has_sitemap = False
        detected_stack: str | None = None

        try:
            robots_resp = self._safe_get(urljoin(self.base_url, "/robots.txt"), use_cache=True)
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
            sitemap_resp = self._safe_get(
                urljoin(self.base_url, "/sitemap.xml"), max_bytes=_MAX_SITEMAP_BYTES, use_cache=True
            )
            has_sitemap = sitemap_resp.status_code == 200
        except (httpx.HTTPError, PrivateNetworkBlockedError) as exc:
            notes.append(f"sitemap.xml 檢查失敗：{exc}")

        try:
            home_resp = self._safe_get(self.base_url, use_cache=True)
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
            resp = self._safe_get(sitemap_url, max_bytes=_MAX_SITEMAP_BYTES, use_cache=True)
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

        # 若這個 URL 剛好是 probe()/list_urls() 已快取過的固定路徑（robots.txt/
        # sitemap.xml/首頁），直接重用結果，不重新發送請求也不用再等 rate limit——
        # 這是同一份內容，不應該被算成第二次「新的」請求。
        cached = self._response_cache.get(url)
        if cached is not None:
            self._register_final_host(cached.final_url)
            retain_body_cached = _is_textual_content_type(
                cached.headers.get("content-type", "")
            )
            return PageSnapshot(
                url=url,
                status_code=cached.status_code,
                final_url=cached.final_url,
                redirect_chain=cached.history,
                headers=cached.headers,
                html=_decode_body(cached) if retain_body_cached else "",
                fetched_at=fetched_at,
                elapsed_ms=0,
            )

        self._rate_limiter.wait()

        redirect_chain: list[str] = []
        start = time.monotonic()
        try:
            resp = self._safe_get(url)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            self._register_final_host(resp.final_url)
            retain_body = _is_textual_content_type(resp.headers.get("content-type", ""))
            return PageSnapshot(
                url=url,
                status_code=resp.status_code,
                final_url=resp.final_url,
                redirect_chain=resp.history,
                headers=resp.headers,
                html=_decode_body(resp) if retain_body else "",
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

    def probe_path(
        self,
        path: str,
        *,
        redact_preview: bool = False,
        signature_check=None,
    ) -> ProbeResult:
        """對 base_url 底下的單一路徑發送一次性 GET 探測，供 Security Mode 的
        暴露檔案/目錄列表檢查使用。與一般頁面爬取共用同一套 SSRF 防護
        （_safe_get 內的 ensure_host_allowed）與 rate limiter，不繞過。

        刻意只回傳極簡化的 ProbeResult（見 models.py 的欄位說明），不回傳
        完整 PageSnapshot：body 上限只有 4KB，且 redact_preview=True 時
        （呼叫端判斷這是已知敏感路徑，如 .env/.git/wp-config 備份）連這一小段
        摘要都不保留，避免任何情況下把可能含密碼/金鑰的檔案內容存進報告。

        redact_preview=True 的路徑一律以 same_origin_only=True 發送：使用者
        只授權掃描這一個網站，若該路徑意外 redirect 到第三方網域，不會追過去
        對未授權的第三方主機發送敏感路徑探測（見 _safe_get 的 same_origin_only）。

        signature_check：可選的 `Callable[[bytes], bool]`，用來判斷內容是否
        真的符合該路徑該有的特徵（例如 .env 該像 KEY=VALUE、.git/HEAD 該以
        "ref: refs/" 開頭），而不是只憑 200 狀態碼就認定「真的洩漏了」——很多
        SPA/WAF 對任何路徑都回 200 的自訂錯誤頁，會讓純看狀態碼的判斷高誤報。
        這個函式在這裡（body 尚未離開 connector 前）被呼叫，回傳值只有布林，
        存進 ProbeResult.content_matches_signature，內容本身不會外流。
        """
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        self._rate_limiter.wait()
        try:
            resp = self._safe_get(url, max_bytes=_MAX_PROBE_BYTES, same_origin_only=redact_preview)
        except (httpx.HTTPError, PrivateNetworkBlockedError) as exc:
            return ProbeResult(path=path, status_code=0, content_type=str(exc)[:200])

        preview = ""
        if not redact_preview and resp.status_code == 200:
            try:
                preview = _decode_body(resp)[:_PROBE_PREVIEW_CHARS]
            except Exception:  # noqa: BLE001 - 摘要是 best-effort，解碼失敗就留空
                preview = ""

        matches_signature = None
        if signature_check is not None and resp.status_code == 200:
            try:
                matches_signature = bool(signature_check(resp.body))
            except Exception:  # noqa: BLE001 - 簽章判斷失敗視為不符合，不因此中斷探測
                matches_signature = False

        return ProbeResult(
            path=path,
            status_code=resp.status_code,
            content_type=resp.headers.get("content-type", ""),
            content_length=len(resp.body) if not resp.truncated else None,
            body_preview=preview,
            truncated=resp.truncated,
            content_matches_signature=matches_signature,
        )

    def close(self) -> None:
        self._client.close()
