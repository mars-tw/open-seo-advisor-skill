"""IndexNow 提交流程統籌：key 驗證 -> URL scope 驗證 -> 分批送出。

這裡把 `key.py`/`validator.py`/`client.py` 三個各自獨立、各自可測試的模組
組成一次完整的提交流程，供 `cli.py` 呼叫。dry_run 模式下只做到 URL 驗證，
不會呼叫 `verify_key_location()`/`submit_batch()`（避免預覽階段就對外
發出網路請求）。
"""

from __future__ import annotations

from seo_advisor.indexnow.client import (
    IndexNowApiError,
    submit_batch,
    verify_key_location,
)
from seo_advisor.indexnow.key import InvalidIndexNowKeyError, validate_key_format
from seo_advisor.indexnow.models import (
    IndexNowSubmissionResult,
    IndexNowUrlValidation,
)
from seo_advisor.indexnow.validator import (
    IndexNowScope,
    InvalidIndexNowScopeError,
    is_url_in_scope,
)
from seo_advisor.security.rate_limiter import RateLimiter

_DEFAULT_BATCH_SIZE = 1000
_DEFAULT_MAX_URLS = 500
_MIN_REQUEST_INTERVAL_SECONDS = 1.0


def run_submission(
    *,
    site: str,
    urls: list[str],
    key: str,
    key_location: str,
    endpoint: str,
    dry_run: bool,
    max_urls: int = _DEFAULT_MAX_URLS,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    allow_private_network: bool = False,
) -> IndexNowSubmissionResult:
    """驗證 key 格式 -> （非 dry-run 時）驗證 keyLocation 可讀取 -> 逐一驗證
    URL scope -> （非 dry-run 時）分批送出。回傳完整結果供 CLI 渲染報告。
    """
    notes: list[str] = []
    validate_key_format(key)

    try:
        scope = IndexNowScope.from_key_location(key_location)
    except InvalidIndexNowScopeError as exc:
        raise IndexNowApiError(f"keyLocation 格式不正確：{exc}") from exc

    if len(urls) > max_urls:
        notes.append(
            f"提交的 URL 數量（{len(urls)}）超過 --max-urls 上限（{max_urls}），"
            f"只會處理前 {max_urls} 筆，其餘已略過。"
        )
        urls = urls[:max_urls]

    url_validations: list[IndexNowUrlValidation] = []
    accepted_urls: list[str] = []
    for url in urls:
        if is_url_in_scope(url, scope):
            url_validations.append(IndexNowUrlValidation(url=url, accepted=True))
            accepted_urls.append(url)
        else:
            url_validations.append(
                IndexNowUrlValidation(
                    url=url, accepted=False, reason="URL 不在 keyLocation 授權範圍內（host/path/scheme 不符）"
                )
            )

    key_verified = False
    batches = []

    if not dry_run:
        verify_key_location(key_location, key, allow_private_network=allow_private_network)
        key_verified = True

        rate_limiter = RateLimiter(_MIN_REQUEST_INTERVAL_SECONDS)
        for batch_index, start in enumerate(range(0, len(accepted_urls), batch_size)):
            chunk = accepted_urls[start : start + batch_size]
            result = submit_batch(
                endpoint=endpoint,
                site_host=scope.host,
                key=key,
                key_location=key_location,
                urls=chunk,
                rate_limiter=rate_limiter,
            )
            batches.append(result.model_copy(update={"batch_index": batch_index}))

    return IndexNowSubmissionResult(
        dry_run=dry_run,
        site=site,
        key_location=key_location,
        key_verified=key_verified,
        endpoint=endpoint,
        submitted_count=len(accepted_urls) if not dry_run else 0,
        skipped_count=len(urls) - len(accepted_urls),
        url_validations=url_validations,
        batches=batches,
        notes=notes,
    )


__all__ = ["run_submission", "InvalidIndexNowKeyError"]
