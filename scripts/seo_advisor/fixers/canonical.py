"""只自動移除目標等價的重複 canonical。不同目標需由站長依掃描證據選定。"""

from __future__ import annotations

import difflib
import re
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from seo_advisor.crawler import CrawlResult
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


def _destination(base: str, href: str) -> str:
    if not href.strip():
        return ""
    parsed = urlsplit(urljoin(base, href.strip()))
    authority = parsed.netloc.lower()
    if parsed.scheme == "https":
        authority = authority.removesuffix(":443")
    elif parsed.scheme == "http":
        authority = authority.removesuffix(":80")
    return urlunsplit((parsed.scheme, authority, parsed.path or "/", parsed.query, ""))


def plan_fix(
    finding: Finding, *, pages: dict[str, str], crawl: CrawlResult | None = None,
    seed_url: str = "",
) -> PatchPlan:
    """產出移除多餘 canonical 標籤的修復計畫。

    pages: {相對路徑: 目前 HTML 內容} 只需包含 finding.affected_urls 涵蓋的頁面。
    """
    targets: list[FixTarget] = []
    warnings: list[str] = []
    decisions: list[str] = []

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

        document = urljoin(seed_url, url)
        base = soup.find("base", href=True)
        base_url = urljoin(document, base["href"]) if base else document
        candidates = {_destination(base_url, tag.get("href") or "") for tag in canonical_tags}
        if len(candidates) != 1 or not all(candidates) or any(urlsplit(c).scheme not in ("", "http", "https") for c in candidates):
            evidence = []
            for candidate in sorted(candidates):
                snapshot = None
                inbound = []
                if crawl is not None:
                    snapshot = next((page for key, page in crawl.pages.items()
                                     if _destination(seed_url, key) == candidate), None)
                    inbound = [source for source, links in crawl.link_graph.items()
                               if any(_destination(seed_url, link) == candidate for link in links)]
                status = f"HTTP {snapshot.status_code}，最終網址 {snapshot.final_url}" if snapshot else "HTTP 與最終網址待查"
                links = "、".join(inbound[:3]) or "本次未觀察到"
                evidence.append(f"{candidate or '空白目標'}（{status}，站內連入：{links}）")
            decisions.append(f"{rel_path}：請確認正規網址，再移除其他標籤。候選：" + "、".join(evidence))
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

    if not targets and not decisions:
        raise NotFixableError(
            f"{finding.id} 沒有找到可修復的頁面內容（可能已經沒有多重 canonical 衝突）。"
        )

    return PatchPlan(
        plan_id=f"fix-{finding.id}",
        finding_id=finding.id,
        fix_type="canonical",
        risk_level="medium",
        targets=targets,
        summary=f"{len(targets)} 頁可移除等價的重複 canonical，{len(decisions)} 頁需確認正規目標。",
        validation_steps=["重新爬取受影響頁面，確認每頁僅剩一個 canonical 標籤"],
        warnings=warnings + decisions,
        suggested_actions=decisions,
        plan_only=not targets,
    )
