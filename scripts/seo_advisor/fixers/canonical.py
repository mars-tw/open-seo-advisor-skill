"""canonical 修復：移除單一頁面裡多餘的重複 canonical 標籤。

對應 analyzers/technical.py 的 `_check_page_metadata`（category: canonical_conflict）
產出的 Finding——頁面有多個 `<link rel="canonical">`，保留第一個、移除其餘。

這是這輪唯一需要修改頁面 HTML 本身結構（而非整檔案取代）的 fixer，因此用
BeautifulSoup 定位並移除多餘標籤，而不是整份內容重寫，讓 diff 盡可能小、
只動需要動的部分。只處理「多重宣告衝突」這種結構清楚的情況，不嘗試判斷
「canonical 該指向哪個 URL 才對」這種需要業務邏輯判斷的問題（那類問題目前
分析器本身也還沒有對應的 Finding 觸發，超出這輪範圍）。
"""

from __future__ import annotations

import difflib
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from seo_advisor.fixers.models import FixTarget, NotFixableError, PatchPlan, ensure_write_target_allowed
from seo_advisor.models import Finding

# 常見樣板引擎語法（Jinja/Django/Handlebars/Liquid/PHP/ASP 等）的粗略偵測。
# BeautifulSoup 重新序列化整份 HTML 時，樣板語法本身雖然通常會被完整保留
# （不在標籤結構內），但屬性順序、空白、自我閉合寫法等會被重新格式化，
# 對於樣板檔案（.html.j2、Django template 等）這種改動風險偏高、且不易讓
# 使用者一眼判斷「差異只在 canonical 標籤」——因此偵測到樣板語法就不自動
# 修復，只留下警告，避免掌控範圍之外的重新序列化影響到其他部分。
_TEMPLATE_SYNTAX_PATTERN = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|<\?php|<%.*?%>")


def _looks_like_template(html: str) -> bool:
    return bool(_TEMPLATE_SYNTAX_PATTERN.search(html))


def _to_relative_path(url: str) -> str:
    """把 Finding.affected_urls 裡的項目（可能是完整 URL 或本地相對路徑）
    轉成 LocalArchiveConnector 認得的相對路徑。LocalArchiveConnector 只掃描
    *.html 檔案（見 connectors/local_archive.py 的 list_urls），因此乾淨網址
    （沒有副檔名，例如 /about）比照同樣的慣例補上 .html。
    """
    parsed = urlparse(url)
    path = parsed.path if parsed.scheme else url
    rel_path = path.lstrip("/") or "index.html"
    if "." not in rel_path.rsplit("/", 1)[-1]:
        rel_path = rel_path.rstrip("/") + ".html"
    return rel_path


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
    return "CANONICAL_CONFLICT" in finding.id


def plan_fix(finding: Finding, *, pages: dict[str, str]) -> PatchPlan:
    """產出移除多餘 canonical 標籤的修復計畫。

    pages: {相對路徑: 目前 HTML 內容} 只需包含 finding.affected_urls 涵蓋的頁面。
    """
    targets: list[FixTarget] = []
    warnings: list[str] = []

    for url in finding.affected_urls:
        rel_path = _to_relative_path(url)
        original = pages.get(url) or pages.get(rel_path)
        if original is None:
            warnings.append(f"找不到 {url} 的內容，已略過此頁面。")
            continue

        if _looks_like_template(original):
            warnings.append(
                f"{rel_path} 看起來含有樣板引擎語法（如 {{{{ }}}}、{{% %}}、<?php 等），"
                "重新序列化整份 HTML 有改動樣板結構的風險，已略過自動修復，"
                "請手動移除多餘的 canonical 標籤。"
            )
            continue

        ensure_write_target_allowed(rel_path)
        soup = BeautifulSoup(original, "lxml")
        canonical_tags = soup.find_all("link", rel="canonical")
        if len(canonical_tags) <= 1:
            continue

        for extra_tag in canonical_tags[1:]:
            extra_tag.decompose()
        fixed = str(soup)

        targets.append(
            FixTarget(
                path=rel_path,
                original_content=original,
                fixed_content=fixed,
                diff_preview=_diff(rel_path, original, fixed),
            )
        )

    if not targets:
        raise NotFixableError(
            f"{finding.id} 沒有找到可修復的頁面內容（可能已經沒有多重 canonical 衝突）。"
        )

    return PatchPlan(
        plan_id=f"fix-{finding.id}",
        finding_id=finding.id,
        fix_type="canonical",
        risk_level="medium",
        targets=targets,
        summary=f"移除 {len(targets)} 個頁面裡多餘的重複 canonical 標籤，只保留第一個。",
        validation_steps=["重新爬取受影響頁面，確認每頁僅剩一個 canonical 標籤"],
        warnings=warnings,
    )
