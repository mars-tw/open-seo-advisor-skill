"""robots.txt 修復：補 Sitemap 宣告、新建缺失的 robots.txt。

對應 analyzers/technical.py 的 `_check_robots_txt`（category: robots_missing /
robots_no_sitemap）產出的 Finding。這個 fixer 只處理「加 Sitemap 宣告」這種
低風險、結構清楚的修改，不解析/改寫使用者既有的 Disallow 規則（那涉及對
使用者爬取策略的判斷，風險較高，這輪不做）。
"""

from __future__ import annotations

import difflib

from seo_advisor.fixers.models import FixTarget, PatchPlan, ensure_write_target_allowed
from seo_advisor.models import Finding

ROBOTS_PATH = "robots.txt"


def _guess_sitemap_url(seed_url: str) -> str:
    base = seed_url.rstrip("/")
    if base.startswith(("http://", "https://")):
        origin = "/".join(base.split("/")[:3])
        return f"{origin}/sitemap.xml"
    return "/sitemap.xml"


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
    # Finding.category 是粗略分組（例如 "indexability"），細分類別實際編碼在
    # finding.id 裡（見 analyzers/technical.py 的 next_id("robots_missing")，
    # 產出 SEO-ROBOTS_MISSING-001），因此判斷要看 id 而非 category。
    return "ROBOTS_MISSING" in finding.id or "ROBOTS_NO_SITEMAP" in finding.id


def plan_fix(finding: Finding, *, current_content: str | None, seed_url: str) -> PatchPlan:
    """產出 robots.txt 的修復計畫。current_content 為 None 代表檔案不存在。"""
    ensure_write_target_allowed(ROBOTS_PATH)
    sitemap_url = _guess_sitemap_url(seed_url)
    sitemap_line = f"Sitemap: {sitemap_url}"

    original = current_content or ""
    if "ROBOTS_MISSING" in finding.id:
        fixed = f"User-agent: *\nAllow: /\n\n{sitemap_line}\n"
        summary = "建立 robots.txt，允許全站爬取並宣告 sitemap 位置。"
        warnings = ["原本沒有 robots.txt，若你的網站有需要阻擋的路徑，請在套用後手動補上 Disallow 規則。"]
    else:
        fixed = original.rstrip("\n") + f"\n\n{sitemap_line}\n"
        summary = "在既有 robots.txt 補上 Sitemap 宣告，不修改任何既有規則。"
        warnings = []

    target = FixTarget(
        path=ROBOTS_PATH,
        original_content=original,
        fixed_content=fixed,
        diff_preview=_diff(ROBOTS_PATH, original, fixed),
    )
    return PatchPlan(
        plan_id=f"fix-{finding.id}",
        finding_id=finding.id,
        fix_type="robots_txt",
        risk_level="low",
        targets=[target],
        summary=summary,
        validation_steps=["重新讀取 robots.txt 並確認內容包含 Sitemap 宣告"],
        warnings=warnings,
    )
