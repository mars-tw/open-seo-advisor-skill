"""sitemap.xml 修復：sitemap 完全缺失時，用已知的正規 URL 清單建立一份。

對應 analyzers/technical.py 的 `_check_sitemap`（category: sitemap_missing）。

這輪只處理「完全缺失」這個結構清楚的情況：用 crawl 階段已經蒐集到的頁面
URL（排除非 200 狀態碼、排除 noindex 頁面）直接產生 `<urlset>`。

`sitemap_too_large`（需要拆成 sitemap index）與 `sitemap_invalid_xml`（需要
先理解原本壞掉的結構才能安全修正，貿然重寫可能丟失使用者原本想保留的
lastmod/priority 等資訊）風險與複雜度都更高，這輪不自動修，維持 plan-only
建議（由 Consultant 報告本身提示問題，等待後續版本強化）。
"""

from __future__ import annotations

import difflib
from xml.sax.saxutils import escape

from seo_advisor.fixers.models import FixTarget, PatchPlan, ensure_write_target_allowed
from seo_advisor.models import Finding

SITEMAP_PATH = "sitemap.xml"


def _diff(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def can_fix(finding: Finding) -> bool:
    return "SITEMAP_MISSING" in finding.id


def plan_fix(finding: Finding, *, indexable_urls: list[str]) -> PatchPlan:
    """產出建立 sitemap.xml 的修復計畫。

    indexable_urls：已爬取且狀態碼 200、非 noindex 的完整 URL 清單，
    由呼叫端（fixers/runner.py）從 CrawlResult 篩選後傳入。
    """
    urls_xml = "\n".join(
        f"  <url>\n    <loc>{escape(url)}</loc>\n  </url>" for url in indexable_urls
    )
    fixed = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls_xml}\n"
        "</urlset>\n"
    )

    ensure_write_target_allowed(SITEMAP_PATH)
    target = FixTarget(
        path=SITEMAP_PATH,
        original_content="",
        fixed_content=fixed,
        diff_preview=_diff(SITEMAP_PATH, "", fixed),
    )

    warnings = []
    if not indexable_urls:
        warnings.append("沒有偵測到任何可索引的 URL，產生的 sitemap 會是空的，建議先確認爬取範圍。")

    return PatchPlan(
        plan_id=f"fix-{finding.id}",
        finding_id=finding.id,
        fix_type="sitemap",
        risk_level="low",
        targets=[target],
        summary=f"建立 sitemap.xml，包含 {len(indexable_urls)} 個已爬取到的可索引 URL。",
        validation_steps=["重新讀取 sitemap.xml 並確認為合法 XML 且可被解析"],
        warnings=warnings,
    )
