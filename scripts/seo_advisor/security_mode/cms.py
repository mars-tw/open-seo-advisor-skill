"""CMS 版本粗略提示：只從公開 HTML/meta 標籤判斷 CMS 種類與版本字串是否
暴露，不查詢任何 CVE/漏洞資料庫。

這是刻意維持的決策，不是尚未實作：查詢 CVE 資料庫（無論是自建/爬取，或
呼叫 WPScan/NVD 等第三方 API）需要維護資料來源、處理 rate limit 與 API
金鑰、且這裡偵測到的「版本號」是粗略字串比對，不是可靠的 plugin/theme
指紋辨識——拿不準確的指紋去查漏洞資料庫，容易產生大量誤導性的漏洞比對
結果，而 Security Mode 的報告一旦寫出「已知 CVE」，使用者往往會直接當成
高信任度的資安結論，錯誤比對的成本遠高於「不做」。

只誠實提示「版本號本身是否公開可見」（這本身就是一種資訊洩漏，攻擊者能
更精準地鎖定已知漏洞），不斷言任何具體漏洞編號、風險等級、或「這個版本
有沒有漏洞」的判斷——偵測到版本資訊公開，只代表資訊洩漏本身的風險，
不是漏洞確認。
"""

from __future__ import annotations

import re

from seo_advisor.security_mode.models import SecurityFinding, SecuritySeverity, SeoImpact

_WP_VERSION_PATTERN = re.compile(r'content="WordPress\s+([\d.]+)"', re.IGNORECASE)
_GENERATOR_PATTERN = re.compile(r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE)


def check_cms_version_exposure(html: str, url: str, next_id) -> list[SecurityFinding]:
    if not html:
        return []

    findings: list[SecurityFinding] = []

    wp_match = _WP_VERSION_PATTERN.search(html)
    if wp_match:
        version = wp_match.group(1)
        findings.append(
            SecurityFinding(
                id=next_id("cms_version_exposed"),
                title=f"WordPress 版本號公開可見：{version}",
                category="cms_version",
                severity=SecuritySeverity.S3_LOW,
                seo_impact=SeoImpact.TRUST,
                confidence=0.5,
                affected_urls=[url],
                evidence={"cms": "wordpress", "version": version},
                recommendation=(
                    "偵測到版本資訊公開可見，這不是漏洞確認，只代表攻擊者能更精準地鎖定"
                    "該版本可能存在的已知漏洞。建議移除或隱藏版本號（多數安全外掛提供此功能），"
                    "並定期確認 WordPress core、外掛、佈景主題都更新到最新版本。本工具不查詢"
                    "任何 CVE/漏洞資料庫，若需要確認實際漏洞狀況，請使用 WPScan 等專業弱點"
                    "掃描工具，或以 WordPress 官方安全公告為準。"
                ),
            )
        )
        return findings

    generator_match = _GENERATOR_PATTERN.search(html)
    if generator_match:
        generator = generator_match.group(1)
        findings.append(
            SecurityFinding(
                id=next_id("cms_generator_exposed"),
                title=f"頁面公開了產生工具資訊：{generator}",
                category="cms_version",
                severity=SecuritySeverity.S3_LOW,
                seo_impact=SeoImpact.TRUST,
                confidence=0.3,
                affected_urls=[url],
                evidence={"generator": generator},
                recommendation="建議評估是否需要移除 generator meta 標籤，減少對外暴露的技術棧資訊。",
            )
        )

    return findings
