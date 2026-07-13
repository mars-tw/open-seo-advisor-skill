"""IndexNow API 呼叫：驗證 key 檔案、批次送出 URL 通知。

API 端點（`submit_batch` 的目標）固定為官方 allowlist，不接受任意端點
URL，這跟 CloudflareConnector 的情境一致：目標主機是官方寫死的，不是
使用者輸入的，因此不需要 `ensure_host_allowed()`。

但 `verify_key_location()` 的目標（`key_location`）不同——那是使用者從
`--key-location` 輸入的網址，工具會對它發出 GET 請求，屬於「使用者可控
目標」，因此套用 `ensure_host_allowed()` 防止指向內網/loopback/雲端
metadata IP（SSRF）。
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from seo_advisor.indexnow.models import IndexNowBatchResult
from seo_advisor.security.network_policy import PrivateNetworkBlockedError, ensure_host_allowed
from seo_advisor.security.rate_limiter import RateLimiter

# IndexNow API 端點：只允許這個 allowlist，不接受任意使用者輸入的端點
# URL（IndexNow 是共用索引，各家搜尋引擎的端點事實上等效，但仍用白名單
# 避免這個參數被誤用成任意 host 的請求轉發工具）。
_ENDPOINTS = {
    "indexnow": "https://api.indexnow.org/indexnow",
    "bing": "https://www.bing.com/indexnow",
}

# 官方協定上限單批 10,000 URL；這裡額外限制單次請求的 body 大小，避免
# 邊界情況下的巨大請求。
_MAX_URLS_PER_BATCH = 10_000
_MAX_KEY_FILE_BYTES = 4 * 1024  # keyLocation 驗證只需要極少量內容

# API 回應大小上限：IndexNow 回應通常沒有 body 或極短，仍保留上限縱深防禦。
_MAX_RESPONSE_BYTES = 1024 * 1024  # 1 MiB


class IndexNowApiError(RuntimeError):
    """IndexNow API 呼叫失敗時的基底例外。"""


class IndexNowKeyVerificationError(IndexNowApiError):
    """keyLocation 驗證失敗（無法讀取、內容不吻合）時拋出。"""


def resolve_endpoint(name: str) -> str:
    if name not in _ENDPOINTS:
        raise IndexNowApiError(
            f"不支援的 IndexNow endpoint {name!r}，只允許：{sorted(_ENDPOINTS.keys())}。"
        )
    return _ENDPOINTS[name]


def verify_key_location(
    key_location: str, key: str, *, timeout_seconds: float = 15.0, allow_private_network: bool = False
) -> None:
    """對 keyLocation 發送一次 GET，確認回應 200 且內容（trim 後）等於
    key。不跟隨跨 host 的 redirect（避免驗證過程被導向到非預期的主機）。

    keyLocation 是使用者輸入的網址，發送請求前先做 SSRF 防護
    （`ensure_host_allowed`），並用 streaming 讀取、超過 `_MAX_KEY_FILE_BYTES`
    立即中止，避免對方回傳異常巨大的內容時整份被讀進記憶體。
    """
    if urlparse(key_location).scheme not in ("http", "https"):
        raise IndexNowKeyVerificationError(f"keyLocation {key_location!r} 必須是 http(s) 網址。")
    try:
        ensure_host_allowed(key_location, allow_private_network=allow_private_network)
    except PrivateNetworkBlockedError as exc:
        raise IndexNowKeyVerificationError(str(exc)) from exc

    base_url = httpx.URL(key_location)
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=False) as client:
            with client.stream("GET", key_location) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location", "")
                    if base_url.join(location).host != base_url.host:
                        raise IndexNowKeyVerificationError(
                            f"keyLocation {key_location!r} 導向了不同主機，為避免驗證被導向"
                            "非預期的位置，已拒絕跟隨。"
                        )
                    raise IndexNowKeyVerificationError(
                        f"keyLocation {key_location!r} 回傳重新導向，請確認網址是否正確"
                        "（IndexNow key 檔案應該直接可讀取，不應該有 redirect）。"
                    )

                if resp.status_code != 200:
                    raise IndexNowKeyVerificationError(
                        f"keyLocation {key_location!r} 回傳狀態碼 {resp.status_code}，預期 200。"
                        "請確認 key 檔案已經上傳到網站上，且可以公開存取。"
                    )

                chunks: list[bytes] = []
                total = 0
                oversized = False
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > _MAX_KEY_FILE_BYTES:
                        oversized = True
                        break
                    chunks.append(chunk)
                body = b"".join(chunks)
    except httpx.HTTPError as exc:
        raise IndexNowKeyVerificationError(f"無法讀取 keyLocation {key_location!r}：{exc}") from exc

    if oversized:
        raise IndexNowKeyVerificationError(
            f"keyLocation {key_location!r} 的內容超過 {_MAX_KEY_FILE_BYTES} bytes，"
            "IndexNow key 檔案應該只包含 key 本身，請確認檔案內容正確。"
        )

    content = body.decode("utf-8", errors="replace").strip()
    if content != key:
        raise IndexNowKeyVerificationError(
            f"keyLocation {key_location!r} 的內容與提供的 key 不一致，"
            "請確認檔案內容就是 key 本身（不含其他文字或空白）。"
        )


def submit_batch(
    *,
    endpoint: str,
    site_host: str,
    key: str,
    key_location: str,
    urls: list[str],
    rate_limiter: RateLimiter,
    timeout_seconds: float = 15.0,
) -> IndexNowBatchResult:
    """對 IndexNow API 送出一批 URL 通知（POST，帶 host/key/keyLocation/
    urlList）。呼叫端負責確保每批不超過 `_MAX_URLS_PER_BATCH`。
    """
    if len(urls) > _MAX_URLS_PER_BATCH:
        raise IndexNowApiError(
            f"單一批次 URL 數量（{len(urls)}）超過協定上限（{_MAX_URLS_PER_BATCH}）。"
        )

    rate_limiter.wait()
    payload = {"host": site_host, "key": key, "keyLocation": key_location, "urlList": urls}

    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=False) as client:
            with client.stream("POST", endpoint, json=payload) as resp:
                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > _MAX_RESPONSE_BYTES:
                        break
                body = b"".join(chunks)
                status_code = resp.status_code
    except httpx.HTTPError as exc:
        return IndexNowBatchResult(
            batch_index=0, url_count=len(urls), status_code=None,
            response_status="request_failed", detail=str(exc),
        )

    status_map = {
        200: "submitted",
        202: "accepted_key_validation_pending",
        400: "invalid_format",
        403: "key_invalid_or_not_found",
        422: "url_not_owned_or_schema_mismatch",
        429: "too_many_requests",
    }
    response_status = status_map.get(status_code, "unexpected_status")
    detail = body.decode("utf-8", errors="replace")[:500] if body else ""

    return IndexNowBatchResult(
        batch_index=0, url_count=len(urls), status_code=status_code,
        response_status=response_status, detail=detail,
    )
