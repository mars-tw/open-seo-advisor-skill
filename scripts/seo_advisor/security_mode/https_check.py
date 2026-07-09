"""HTTPS/TLS 檢查：憑證有效性、HSTS、mixed content。

憑證檢查使用 Python 內建 ssl/socket 直接連線 443（httpx 不易取得完整憑證
細節），連線前仍呼叫 ensure_host_allowed() 做 SSRF 防護，與其他模組一致；
只讀取憑證 metadata，不做任何弱密碼套件掃描或協定降級測試（那類屬於主動
滲透測試範疇，不在 Security Mode 的被動掃描定位內）。
"""

from __future__ import annotations

import socket
import ssl
from datetime import datetime, timezone
from urllib.parse import urlparse

from seo_advisor.security.network_policy import PrivateNetworkBlockedError, ensure_host_allowed
from seo_advisor.security_mode.models import SecurityFinding, SecuritySeverity, SeoImpact

_CONNECT_TIMEOUT_SECONDS = 10.0


def check_certificate(url: str, next_id) -> list[SecurityFinding]:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return [
            SecurityFinding(
                id=next_id("no_https"),
                title="網站未使用 HTTPS",
                category="https",
                severity=SecuritySeverity.S1_HIGH,
                seo_impact=SeoImpact.TRUST,
                confidence=1.0,
                affected_urls=[url],
                evidence={"scheme": parsed.scheme},
                recommendation="Google 將 HTTPS 列為排名訊號之一，且瀏覽器會對 HTTP 網站顯示「不安全」警告，建議盡快導入 HTTPS。",
            )
        ]

    hostname = parsed.hostname or ""
    port = parsed.port or 443

    try:
        ensure_host_allowed(url, allow_private_network=False)
    except PrivateNetworkBlockedError as exc:
        return [
            SecurityFinding(
                id=next_id("https_check_skipped"),
                title="憑證檢查已略過",
                category="https",
                severity=SecuritySeverity.S3_LOW,
                seo_impact=SeoImpact.TRUST,
                confidence=1.0,
                affected_urls=[url],
                evidence={"reason": str(exc)},
                recommendation="此網址指向私有/受限網段，已略過憑證檢查。",
            )
        ]

    findings: list[SecurityFinding] = []
    context = ssl.create_default_context()
    try:
        with socket.create_connection((hostname, port), timeout=_CONNECT_TIMEOUT_SECONDS) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
                tls_version = ssock.version()
    except ssl.SSLCertVerificationError as exc:
        findings.append(
            SecurityFinding(
                id=next_id("cert_invalid"),
                title="TLS 憑證驗證失敗",
                category="https",
                severity=SecuritySeverity.S0_CRITICAL,
                seo_impact=SeoImpact.TRUST,
                confidence=0.9,
                affected_urls=[url],
                evidence={"error": str(exc)},
                recommendation="瀏覽器會對此網站顯示安全警告，嚴重影響信任與流量，請立即檢查憑證設定（是否過期、鏈不完整、網域不符）。",
            )
        )
        return findings
    except (socket.timeout, socket.gaierror, ConnectionError, OSError) as exc:
        findings.append(
            SecurityFinding(
                id=next_id("cert_check_failed"),
                title="無法連線進行憑證檢查",
                category="https",
                severity=SecuritySeverity.S3_LOW,
                seo_impact=SeoImpact.TRUST,
                confidence=0.5,
                affected_urls=[url],
                evidence={"error": str(exc)},
                recommendation="連線逾時或失敗，無法確認憑證狀態，建議稍後重試或人工檢查。",
            )
        )
        return findings

    expiry_str = cert.get("notAfter")
    if expiry_str:
        expiry = datetime.strptime(expiry_str, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        days_left = (expiry - datetime.now(timezone.utc)).days
        if days_left < 0:
            findings.append(
                SecurityFinding(
                    id=next_id("cert_expired"),
                    title="TLS 憑證已過期",
                    category="https",
                    severity=SecuritySeverity.S0_CRITICAL,
                    seo_impact=SeoImpact.TRUST,
                    confidence=1.0,
                    affected_urls=[url],
                    evidence={"expired_on": expiry_str},
                    recommendation="憑證已過期，瀏覽器會完全阻擋訪問，請立即更新憑證。",
                )
            )
        elif days_left < 14:
            findings.append(
                SecurityFinding(
                    id=next_id("cert_expiring_soon"),
                    title=f"TLS 憑證即將於 {days_left} 天內到期",
                    category="https",
                    severity=SecuritySeverity.S1_HIGH,
                    seo_impact=SeoImpact.TRUST,
                    confidence=1.0,
                    affected_urls=[url],
                    evidence={"expires_on": expiry_str, "days_left": days_left},
                    recommendation="建議盡快更新憑證（或確認自動續約是否正常運作），避免到期後網站無法訪問。",
                )
            )

    if tls_version in ("TLSv1", "TLSv1.1"):
        findings.append(
            SecurityFinding(
                id=next_id("tls_outdated"),
                title=f"使用已過時的 TLS 版本：{tls_version}",
                category="https",
                severity=SecuritySeverity.S2_MEDIUM,
                seo_impact=SeoImpact.TRUST,
                confidence=0.9,
                affected_urls=[url],
                evidence={"tls_version": tls_version},
                recommendation="建議停用 TLS 1.0/1.1，只保留 TLS 1.2 以上版本（主流瀏覽器已不支援更早版本）。",
            )
        )

    return findings


def check_hsts(headers: dict[str, str], url: str, next_id) -> list[SecurityFinding]:
    if urlparse(url).scheme != "https":
        return []
    hsts_header = headers.get("strict-transport-security", "")
    if hsts_header:
        return []
    return [
        SecurityFinding(
            id=next_id("hsts_missing"),
            title="未設定 HSTS（Strict-Transport-Security）",
            category="https",
            severity=SecuritySeverity.S3_LOW,
            seo_impact=SeoImpact.TRUST,
            confidence=0.9,
            affected_urls=[url],
            evidence={},
            recommendation="建議加上 Strict-Transport-Security header，強制瀏覽器往後一律用 HTTPS 連線，降低被降級攻擊的風險。",
        )
    ]


def check_mixed_content(html: str, url: str, next_id) -> list[SecurityFinding]:
    if urlparse(url).scheme != "https" or not html:
        return []

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    insecure_assets: list[str] = []
    for tag, attr in (("img", "src"), ("script", "src"), ("link", "href"), ("iframe", "src")):
        for el in soup.find_all(tag):
            value = el.get(attr, "")
            if value.startswith("http://"):
                insecure_assets.append(value)

    if not insecure_assets:
        return []

    return [
        SecurityFinding(
            id=next_id("mixed_content"),
            title=f"偵測到 {len(insecure_assets)} 個透過 HTTP（非 HTTPS）載入的資源",
            category="https",
            severity=SecuritySeverity.S2_MEDIUM,
            seo_impact=SeoImpact.TRUST,
            confidence=0.8,
            affected_urls=[url],
            evidence={"count": len(insecure_assets), "sample": insecure_assets[:5]},
            recommendation="HTTPS 頁面載入 HTTP 資源會被瀏覽器標示為不安全，甚至阻擋載入，請把這些資源網址改成 https://。",
        )
    ]
