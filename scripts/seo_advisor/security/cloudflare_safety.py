"""CloudflareConnector 的輸入驗證：zone_id 格式、redirect rule 安全子集
限制。

背景：Cloudflare API 的請求目標固定是官方端點
`https://api.cloudflare.com/client/v4`（不是使用者輸入的任意網址），因此
這裡的威脅模型跟其他 connector「防止使用者輸入的目標網址造成 SSRF」不同
——真正的風險是 zone_id 被錯誤或惡意拼接進 API path、以及 redirect rule
若允許任意 Cloudflare expression/target，可能被用來建立開放重導或影響
使用者完全沒授權的其他站台。因此這裡改用「輸入格式白名單 + 安全子集」
的防護策略，而非網路層 SSRF 檢查。
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Cloudflare zone_id 固定是 32 字元的小寫十六進位字串，不接受任何其他格式
# ——這條防線避免 zone_id 被當成可以拼接任意路徑片段的字串使用。
_ZONE_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")

# redirect rule 的 path 只允許安全的 exact-match 表達式，不接受任何自訂
# Cloudflare expression 語法（IP/country/bot/device 條件、動態 target
# 等），避免 connector 被當成任意規則注入工具。
_SAFE_PATH_PATTERN = re.compile(r"^/[A-Za-z0-9\-._~/%]*$")


class InvalidZoneIdError(ValueError):
    """zone_id 格式不符合 Cloudflare 官方格式（32 字元小寫十六進位）時拋出。"""


class UnsafeRedirectRuleError(ValueError):
    """redirect rule 的來源路徑或目標網址超出安全子集範圍時拋出。"""


def validate_zone_id(zone_id: str) -> None:
    if not _ZONE_ID_PATTERN.match(zone_id):
        raise InvalidZoneIdError(
            f"zone_id {zone_id!r} 格式不正確。Cloudflare zone_id 固定是 32 字元的"
            "小寫十六進位字串，請從 Cloudflare Dashboard 的 Overview 頁面複製正確的 Zone ID。"
        )


def validate_redirect_source_path(source_path: str) -> None:
    """驗證 redirect rule 的來源路徑：只允許安全的絕對路徑 exact-match，
    不允許查詢字串、fragment、或任何 Cloudflare expression 語法。
    """
    if not source_path.startswith("/"):
        raise UnsafeRedirectRuleError(
            f"redirect rule 的來源路徑 {source_path!r} 必須以 '/' 開頭（絕對路徑）。"
        )
    if "?" in source_path or "#" in source_path:
        raise UnsafeRedirectRuleError(
            f"redirect rule 的來源路徑 {source_path!r} 不可包含查詢字串或 fragment，"
            "這個 MVP 只支援路徑的 exact-match 重導。"
        )
    if not _SAFE_PATH_PATTERN.match(source_path):
        raise UnsafeRedirectRuleError(
            f"redirect rule 的來源路徑 {source_path!r} 含有不允許的字元。"
        )


def validate_redirect_target_url(target_url: str, *, allowed_hosts: frozenset[str]) -> None:
    """驗證 redirect rule 的目標網址：必須是 HTTPS、不含 userinfo、host 必須
    落在使用者的 zone 授權範圍內（apex 或 www，不允許導到任意第三方網域，
    避免 connector 被用來建立開放重導攻擊他人網站）。
    """
    parsed = urlparse(target_url)
    if parsed.scheme != "https":
        raise UnsafeRedirectRuleError(
            f"redirect rule 的目標網址 {target_url!r} 必須是 https://，不允許明文 http。"
        )
    if parsed.username or parsed.password:
        raise UnsafeRedirectRuleError(
            f"redirect rule 的目標網址 {target_url!r} 不可包含帳號密碼資訊。"
        )
    if not parsed.hostname:
        raise UnsafeRedirectRuleError(f"redirect rule 的目標網址 {target_url!r} 缺少主機名稱。")
    if parsed.hostname.lower() not in allowed_hosts:
        raise UnsafeRedirectRuleError(
            f"redirect rule 的目標網址 {target_url!r} 指向 {parsed.hostname!r}，"
            f"不在這個 zone 的授權網域範圍內（{sorted(allowed_hosts)}）。"
            "為避免建立開放重導攻擊他人網站，CloudflareConnector 只允許重導到"
            "自己 zone 底下的網域。"
        )
