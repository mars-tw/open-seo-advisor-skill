"""WordPressAPIConnector：透過 WordPress REST API 唯讀盤點網站內容，並用一般
公開 HTTP 請求（無認證）抓取實際渲染後的頁面供 SEO 分析。

這份設計經過 NORA（Codex）與 Grok 兩個獨立模型兩輪交叉審查定案，MVP 範圍：

- 只做 `read_urls`，capabilities() 只回報 `{"read_urls"}`。不做寫入（更新
  post/page 屬於未來的 `write_content` capability，不是 `write_files`）、
  不做 OAuth（只支援 Application Password）、不做 CVE 查詢、不做
  wp-admin scraping。
- REST API 回傳的 `link` 欄位一律視為 attacker-controlled 輸入：資料庫被
  注入或惡意外掛都可能竄改這個欄位，讓它指向雲端 metadata IP、內網服務、
  或完全無關的第三方網站。因此 `list_urls()` 出口與 `fetch_url()` 入口都會
  用 security/wp_url_scope.py 的 `is_url_in_scope()` 做 scope allowlist
  檢查，不合格的一律丟棄，絕不進入爬取流程；授權範圍在 `__init__` 時完全
  鎖定，不會因為任何 REST 回傳資料或 redirect 而動態擴大。
- 認證的 REST 請求（帶 Application Password）完全不 follow redirect：
  Basic Auth 在有模糊 redirect 規則時是憑證洩漏的經典坑，收到 3xx 直接
  報錯提示使用者確認 base_url 是否正確。公開頁面的 fetch（不帶認證）才
  手動追蹤 redirect，且每一跳都重新做 scope + SSRF 檢查。
- WP connector 只處理「公開已發布的前台內容」：REST 查詢固定用
  status=publish + context=view，Application Password 只用來讀取
  posts/pages 清單與驗證認證是否有效，不會被用來抓 draft/private/需要
  登入才能看的頁面。
- 分頁的迴圈上限只信任呼叫端傳入的 limit/max_items，不信任 WordPress
  回傳的 X-WP-TotalPages（惡意站台可回傳誇大分頁數造成請求放大）。
  REST response 與 public HTML fetch 都有位元組數上限（_fields 參數不是
  安全邊界，惡意伺服器可以無視它塞入超大 JSON）。
"""

from __future__ import annotations

import math
from urllib.parse import urljoin, urlparse

import httpx

from seo_advisor.connectors.base import WebsiteConnector
from seo_advisor.errors import redact_secrets
from seo_advisor.models import ConnectorProfile, PageSnapshot, SafetyPolicy, UrlRecord
from seo_advisor.security.network_policy import PrivateNetworkBlockedError, ensure_host_allowed
from seo_advisor.security.rate_limiter import RateLimiter
from seo_advisor.security.wp_url_scope import WordPressScope, is_url_in_scope

# REST JSON response 大小上限：_fields 參數只是「請求少一點欄位」的最佳化提示，
# 不是安全邊界，惡意伺服器可以無視它在單一欄位塞入超大內容。
_MAX_REST_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MiB
# 公開頁面 fetch 的大小上限，與 HTTPConnector 一致。
_MAX_HTML_BYTES = 10 * 1024 * 1024  # 10 MiB
_MAX_REDIRECTS = 10
_MAX_PER_PAGE = 100


class WordPressConnectorError(RuntimeError):
    """WordPressAPIConnector 相關操作失敗時的基底例外。"""


class WordPressRestUnavailableError(WordPressConnectorError):
    """/wp-json/ 探測失敗：可能不是 WordPress、REST 被停用、或被安全外掛阻擋。"""


class WordPressAuthError(WordPressConnectorError):
    """401：Application Password 或帳號錯誤。"""


class WordPressPermissionError(WordPressConnectorError):
    """403：帳號有效但權限不足，或安全外掛/WAF 阻擋了 REST 請求。"""


class WordPressApiError(WordPressConnectorError):
    """5xx、逾時、或回傳內容不是合法 JSON 等其他 API 層錯誤。"""


def _redacted(exc: Exception) -> str:
    return redact_secrets(str(exc))


class WordPressAPIConnector(WebsiteConnector):
    """透過 WordPress REST API 唯讀盤點 posts/pages，並用無認證的公開請求
    抓取實際渲染後的 HTML 供既有的 SEO 分析器使用。
    """

    def __init__(
        self,
        base_url: str,
        *,
        username: str | None = None,
        app_password: str | None = None,
        policy: SafetyPolicy | None = None,
        timeout_seconds: float = 15.0,
        max_items: int = 500,
        allow_insecure_local_dev: bool = False,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.policy = policy or SafetyPolicy(allowed_capabilities={"read_urls"})

        if (username is None) != (app_password is None):
            raise WordPressConnectorError(
                "username 與 app_password 必須同時提供或同時省略（省略兩者代表"
                "以匿名唯讀模式連線，僅能讀取該站公開的 REST 資料）。"
            )

        self._scope = WordPressScope.from_base_url(base_url)
        parsed = urlparse(base_url)

        is_https = self._scope.scheme == "https"
        is_private_target = self.policy.allow_private_network
        if not is_https and not (is_private_target and allow_insecure_local_dev):
            raise WordPressConnectorError(
                f"base_url {base_url!r} 不是 HTTPS。Application Password 透過 HTTP "
                "Basic Auth 傳輸，公開網際網路上使用 http:// 會讓密碼以明文方式"
                "在網路上傳送。若這是本機/內網開發環境，請同時設定 "
                "SafetyPolicy.allow_private_network=True 與 allow_insecure_local_dev=True。"
            )

        ensure_host_allowed(base_url, allow_private_network=self.policy.allow_private_network)

        self._base_origin = f"{parsed.scheme}://{parsed.netloc}"
        self._rest_root = urljoin(self._base_origin + "/", self._scope.path_prefix.lstrip("/") + "/wp-json/")
        self._username = username
        self._app_password = app_password
        self._max_items = max_items
        self._rate_limiter = rate_limiter or RateLimiter(self.policy.rate_limit_per_second)

        verify_tls = not (is_private_target and allow_insecure_local_dev and not is_https)
        # 認證 REST 請求：follow_redirects=False，收到 3xx 一律視為錯誤，絕不
        # 手動追蹤——Basic Auth 在模糊的 redirect 規則下是憑證洩漏的經典坑。
        self._rest_client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            verify=verify_tls,
        )
        # 公開頁面 fetch：完全不帶 WP 認證，redirect 由 _fetch_public 手動追蹤
        # 並在每一跳重新檢查 scope + SSRF。
        self._public_client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            verify=verify_tls,
        )

    def id(self) -> str:
        return f"wordpress:{self._scope.host}"

    def capabilities(self) -> set[str]:
        return {"read_urls"}

    def close(self) -> None:
        self._rest_client.close()
        self._public_client.close()

    # ------------------------------------------------------------------
    # REST 請求 helper
    # ------------------------------------------------------------------

    def _rest_auth(self) -> httpx.BasicAuth | None:
        if self._username is None:
            return None
        return httpx.BasicAuth(self._username, self._app_password)

    def _rest_get(self, path: str, *, params: dict | None = None) -> httpx.Response:
        """對 REST API 發送一次 GET 請求：不 follow redirect，body 大小受限，
        非預期的 3xx/5xx/連線錯誤都轉成專用例外，且例外訊息一律經過
        redact_secrets() 處理。
        """
        url = urljoin(self._rest_root, path.lstrip("/"))
        self._rate_limiter.wait()
        try:
            with self._rest_client.stream(
                "GET", url, params=params, auth=self._rest_auth()
            ) as resp:
                if 300 <= resp.status_code < 400:
                    raise WordPressApiError(
                        f"REST 請求收到重新導向（{resp.status_code}），這通常代表 "
                        "base_url 填的不是 WordPress 網站的實際根網址（常見情況：www/apex "
                        "或 http/https 版本不一致）。請改用瀏覽器打開後看到的最終網址重試，"
                        "本連線不會自動跟隨重新導向（避免帳密被送到未經授權的主機）。"
                    )
                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > _MAX_REST_RESPONSE_BYTES:
                        raise WordPressApiError(
                            "REST 回應內容超過大小上限，已中止讀取（可能是異常或惡意的回應）。"
                        )
                body = b"".join(chunks)
        except httpx.TimeoutException as exc:
            raise WordPressApiError(f"REST 請求逾時：{_redacted(exc)}") from exc
        except httpx.HTTPError as exc:
            raise WordPressApiError(f"REST 請求失敗：{_redacted(exc)}") from exc

        if resp.status_code == 401:
            raise WordPressAuthError(
                "認證失敗（401）。請確認帳號與 Application Password 是否正確，"
                "或該帳號的 Application Password 是否已在 WordPress 後台啟用。"
            )
        if resp.status_code == 403:
            raise WordPressPermissionError(
                "權限不足或請求被阻擋（403）。可能是帳號權限不夠、或安全外掛/WAF "
                "阻擋了 REST API 請求。"
            )
        if resp.status_code == 404:
            raise WordPressRestUnavailableError(
                f"找不到 REST 端點（404）：{path}。這個網站可能不是 WordPress、"
                "REST API 已被外掛停用、或安全外掛封鎖了這個路由。"
            )
        if resp.status_code >= 500:
            raise WordPressApiError(f"WordPress 網站回傳伺服器錯誤（{resp.status_code}）：{path}")
        if resp.status_code != 200:
            raise WordPressApiError(f"REST 請求收到非預期的狀態碼 {resp.status_code}：{path}")

        response = httpx.Response(
            status_code=resp.status_code, headers=resp.headers, content=body, request=resp.request
        )
        return response

    # ------------------------------------------------------------------
    # WebsiteConnector 介面
    # ------------------------------------------------------------------

    def probe(self) -> ConnectorProfile:
        notes: list[str] = []
        try:
            root_resp = self._rest_get("")
        except WordPressConnectorError as exc:
            raise WordPressRestUnavailableError(
                f"無法連線到 WordPress REST API（{self._rest_root}）：{exc}"
            ) from exc

        try:
            root_json = root_resp.json()
        except ValueError as exc:
            raise WordPressRestUnavailableError(
                f"{self._rest_root} 沒有回傳合法的 JSON，這個網站可能不是 WordPress，"
                "或 REST API 已被停用/封鎖。"
            ) from exc

        namespaces = root_json.get("namespaces", []) if isinstance(root_json, dict) else []
        if isinstance(namespaces, list) and namespaces:
            notes.append(f"偵測到 REST namespace：{', '.join(str(n) for n in namespaces[:10])}")

        auth_verified = False
        if self._username is not None:
            try:
                self._rest_get("wp/v2/posts", params={"per_page": 1, "status": "publish", "_fields": "id"})
                auth_verified = True
                notes.append("Application Password 認證有效（已用 posts 端點驗證）。")
            except WordPressAuthError:
                raise
            except (WordPressPermissionError, WordPressRestUnavailableError) as exc:
                notes.append(
                    f"無法用 posts 端點驗證認證是否有效（{exc}），"
                    "後續讀取可能因權限不足而受限。"
                )

        return ConnectorProfile(
            source_type="wordpress",
            detected_stack="wordpress",
            has_sitemap=False,
            has_robots_txt=False,
            notes=notes
            + (
                []
                if auth_verified or self._username is None
                else ["提醒：建議使用僅有必要權限的專用帳號建立 Application Password，避免使用管理員帳號。"]
            ),
        )

    def list_urls(self, seed: str, limit: int) -> list[UrlRecord]:
        cap = min(limit, self._max_items) if limit > 0 else self._max_items
        records: list[UrlRecord] = []
        skipped_out_of_scope: list[str] = []

        for post_type, source_label in (("posts", "wordpress_rest:post"), ("pages", "wordpress_rest:page")):
            if len(records) >= cap:
                break
            remaining = cap - len(records)
            records.extend(
                self._list_post_type(post_type, source_label, remaining, skipped_out_of_scope)
            )

        return records[:cap]

    def _list_post_type(
        self, post_type: str, source_label: str, remaining_cap: int, skipped: list[str]
    ) -> list[UrlRecord]:
        if remaining_cap <= 0:
            return []
        records: list[UrlRecord] = []
        per_page = min(_MAX_PER_PAGE, remaining_cap)
        max_pages = math.ceil(remaining_cap / per_page) if per_page > 0 else 0

        for page in range(1, max_pages + 1):
            if len(records) >= remaining_cap:
                break
            try:
                resp = self._rest_get(
                    f"wp/v2/{post_type}",
                    params={
                        "status": "publish",
                        "context": "view",
                        "per_page": per_page,
                        "page": page,
                        "_fields": "id,link,slug,type,status,modified_gmt,title",
                    },
                )
            except WordPressRestUnavailableError:
                # 常見情境：這個 post_type 的路由不存在（例如自訂安裝停用了 pages）。
                break
            except WordPressConnectorError:
                break

            try:
                items = resp.json()
            except ValueError:
                break
            if not isinstance(items, list) or not items:
                break

            has_next_page = len(items) >= per_page

            for item in items:
                if len(records) >= remaining_cap:
                    break
                link = item.get("link") if isinstance(item, dict) else None
                if not isinstance(link, str) or not link:
                    continue
                # REST 回傳的 link 視為 attacker-controlled：未通過 scope
                # allowlist 前絕不能進入 UrlRecord / 後續 crawler。
                if not is_url_in_scope(link, self._scope):
                    skipped.append(link)
                    continue
                records.append(UrlRecord(url=link, source=source_label, discovered_depth=0))

            if not has_next_page:
                break

        return records

    def fetch_url(self, url: str, *, render: bool = False, fetched_at: str = "") -> PageSnapshot:
        if render:
            raise NotImplementedError(
                "render=True 需要 Playwright 支援，WordPressAPIConnector 尚未實作。"
            )

        if not is_url_in_scope(url, self._scope):
            return PageSnapshot(
                url=url,
                status_code=0,
                final_url=url,
                html="",
                fetched_at=fetched_at,
                fetch_error_type="out_of_scope",
                fetch_error_message=(
                    "這個網址不在 WordPressAPIConnector 授權的範圍內（host/scheme/port/"
                    "path 其中一項不符），為避免存取未授權的主機，已拒絕發送請求。"
                ),
            )

        self._rate_limiter.wait()
        try:
            return self._fetch_public(url, fetched_at=fetched_at)
        except PrivateNetworkBlockedError as exc:
            return PageSnapshot(
                url=url,
                status_code=0,
                final_url=url,
                html="",
                fetched_at=fetched_at,
                fetch_error_type="private_network_blocked",
                fetch_error_message=_redacted(exc),
            )
        except httpx.TimeoutException as exc:
            return PageSnapshot(
                url=url,
                status_code=0,
                final_url=url,
                html="",
                fetched_at=fetched_at,
                fetch_error_type="timeout",
                fetch_error_message=_redacted(exc),
            )
        except httpx.HTTPError as exc:
            return PageSnapshot(
                url=url,
                status_code=0,
                final_url=url,
                html="",
                fetched_at=fetched_at,
                fetch_error_type=type(exc).__name__,
                fetch_error_message=_redacted(exc),
            )

    def _fetch_public(self, url: str, *, fetched_at: str) -> PageSnapshot:
        """無認證的公開頁面請求：手動追蹤 redirect，每一跳都重新檢查 scope 與
        SSRF（不擴大授權範圍），並對 body 做串流大小上限保護。
        """
        redirect_chain: list[str] = []
        current = url
        for _ in range(_MAX_REDIRECTS + 1):
            if not is_url_in_scope(current, self._scope):
                return PageSnapshot(
                    url=url,
                    status_code=0,
                    final_url=current,
                    redirect_chain=redirect_chain,
                    html="",
                    fetched_at=fetched_at,
                    fetch_error_type="redirect_out_of_scope",
                    fetch_error_message=(
                        f"重新導向目標 {current!r} 超出授權範圍，已停止追蹤（不會擴大"
                        "授權範圍）。"
                    ),
                )
            ensure_host_allowed(current, allow_private_network=self.policy.allow_private_network)

            with self._public_client.stream("GET", current) as resp:
                if resp.is_redirect and resp.headers.get("location"):
                    redirect_chain.append(str(resp.url))
                    current = urljoin(current, resp.headers["location"])
                    continue

                chunks: list[bytes] = []
                total = 0
                truncated = False
                for chunk in resp.iter_bytes():
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > _MAX_HTML_BYTES:
                        truncated = True
                        break
                body = b"".join(chunks) if not truncated else b"".join(chunks)[:_MAX_HTML_BYTES]

                is_html = "text/html" in resp.headers.get("content-type", "")
                html_text = ""
                if is_html:
                    try:
                        html_text = body.decode(resp.encoding or "utf-8", errors="replace")
                    except (LookupError, ValueError):
                        html_text = body.decode("utf-8", errors="replace")

                return PageSnapshot(
                    url=url,
                    status_code=resp.status_code,
                    final_url=str(resp.url),
                    redirect_chain=redirect_chain,
                    headers=dict(resp.headers),
                    html=html_text,
                    fetched_at=fetched_at,
                )

        return PageSnapshot(
            url=url,
            status_code=0,
            final_url=current,
            redirect_chain=redirect_chain,
            html="",
            fetched_at=fetched_at,
            fetch_error_type="too_many_redirects",
            fetch_error_message=f"重新導向次數超過上限（{_MAX_REDIRECTS}）。",
        )
