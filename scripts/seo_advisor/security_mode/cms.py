"""CMS 版本粗略提示：只從公開 HTML/meta 標籤判斷 CMS 種類與版本字串是否
暴露，不查詢任何 CVE/漏洞資料庫（那需要維護資料來源與更新頻率，這輪評估
成本過高、且容易給出過時或不準確的漏洞資訊，反而誤導使用者）。

只誠實提示「版本號本身是否公開可見」（這本身就是一種資訊洩漏，攻擊者能
更精準地鎖定已知漏洞），不斷言任何具體漏洞編號或風險等級判斷。
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
                    "頁面 meta generator 標籤公開了 WordPress 版本號，這讓攻擊者能更精準地鎖定"
                    "該版本的已知漏洞。建議移除或隱藏版本號（多數安全外掛提供此功能），"
                    "並定期確認 WordPress core、外掛、佈景主題都更新到最新版本"
                    "（本工具不查詢即時漏洞資料庫，請以 WordPress 官方安全公告為準）。"
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
