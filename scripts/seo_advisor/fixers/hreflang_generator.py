"""hreflang HTML 產生器：依使用者提供的語言對照表，在指定頁面插入/整組
替換 `<link rel="alternate" hreflang="...">` 標籤。

跟既有 `fixers/canonical.py` 一樣使用 BeautifulSoup 定位插入點、只改動
`<head>` 內的 hreflang link 區塊，讓 diff 盡可能小；跟 canonical.py 一樣
偵測樣板引擎語法（Jinja/Django/PHP/ASP 等）就降級為 plan_only，避免重新
序列化整份 HTML 影響樣板結構。

跟 v0.2.6 `fixers/hreflang.py`（plan_only 建議）的關係見 `hreflang_map.py`
模組說明：那裡處理「掃描發現問題但不知道正確答案」，這裡處理「使用者已經
提供正確答案，直接產生」。這裡不是從 Finding 驅動，`plan_id`/`finding_id`
用固定字首標示「使用者主動觸發的產生器」。
"""

from __future__ import annotations

import difflib
import re

from bs4 import BeautifulSoup

from seo_advisor.fixers.hreflang_map import HreflangMap, render_hreflang_tags
from seo_advisor.fixers.models import FixTarget, PatchPlan, ensure_write_target_allowed

_TEMPLATE_SYNTAX_PATTERN = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|<\?php|<%.*?%>")
_GENERATED_FINDING_ID = "hreflang-generator-user-provided-map"


def _looks_like_template(html: str) -> bool:
    return bool(_TEMPLATE_SYNTAX_PATTERN.search(html))


def _diff(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def _insert_hreflang_block(soup: BeautifulSoup, tag_htmls: list[str]) -> None:
    """移除既有的 hreflang alternate link（整組替換，不做部分保留——見
    模組說明：使用者提供的語言對照表視為權威資料，部分保留舊標籤反而
    可能讓錯誤/過期的宣告留下來）。插入點：canonical 標籤之後；沒有
    canonical 就放在 <title> 之後；都沒有就放在 <head> 開頭。
    """
    head = soup.find("head")
    if head is None:
        raise _MissingHeadError("找不到 <head> 標籤。")

    for tag in head.find_all("link", rel="alternate", hreflang=True):
        tag.decompose()

    new_tags = [BeautifulSoup(html, "html.parser") for html in tag_htmls]

    canonical = head.find("link", rel="canonical")
    if canonical is not None:
        for new_tag in reversed(new_tags):
            canonical.insert_after(new_tag)
        return

    title = head.find("title")
    if title is not None:
        for new_tag in reversed(new_tags):
            title.insert_after(new_tag)
        return

    for new_tag in reversed(new_tags):
        head.insert(0, new_tag)


class _MissingHeadError(ValueError):
    """頁面找不到 <head> 標籤時拋出（內部用，轉換成 plan_only 警告）。"""


def build_hreflang_html_plan(hreflang_map: HreflangMap, *, pages: dict[str, str]) -> PatchPlan:
    """產出插入 hreflang 標籤的修復計畫。

    pages：{相對路徑: 目前 HTML 內容}，只需包含語言對照表裡有 `targets`
        指定的頁面（呼叫端負責讀取這些檔案內容，例如透過 connector）。
    只有同時滿足以下條件的頁面會產出可自動套用的 target：
    - cluster 有為該語言代碼指定 targets 路徑
    - pages 裡有該路徑的內容
    - 內容不含樣板引擎語法
    - 找得到 <head> 標籤
    其餘情況降級為警告，寫進 plan.warnings，不會中斷整個流程。
    """
    targets: list[FixTarget] = []
    warnings: list[str] = []
    skipped_no_target = 0

    for cluster in hreflang_map.clusters:
        tag_htmls = render_hreflang_tags(cluster.alternates)

        if not cluster.targets:
            skipped_no_target += 1
            continue

        for code, rel_path in cluster.targets.items():
            original = pages.get(rel_path)
            if original is None:
                warnings.append(f"cluster {cluster.cluster_id!r}（{code}）：找不到 {rel_path!r} 的內容，已略過。")
                continue

            if _looks_like_template(original):
                warnings.append(
                    f"cluster {cluster.cluster_id!r}（{code}）：{rel_path!r} 看起來含有樣板引擎語法"
                    "（如 {{ }}、{% %}、<?php 等），重新序列化整份 HTML 有改動樣板結構的風險，"
                    "已略過自動修復，請手動插入 hreflang 標籤。"
                )
                continue

            try:
                ensure_write_target_allowed(rel_path)
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"cluster {cluster.cluster_id!r}（{code}）：{exc}")
                continue

            soup = BeautifulSoup(original, "lxml")
            try:
                _insert_hreflang_block(soup, tag_htmls)
            except _MissingHeadError:
                warnings.append(
                    f"cluster {cluster.cluster_id!r}（{code}）：{rel_path!r} 找不到 <head> 標籤，"
                    "已略過自動修復，請手動插入 hreflang 標籤。"
                )
                continue
            fixed = str(soup)

            targets.append(
                FixTarget(
                    path=rel_path,
                    original_content=original,
                    fixed_content=fixed,
                    diff_preview=_diff(rel_path, original, fixed),
                )
            )

    if skipped_no_target:
        warnings.append(
            f"{skipped_no_target} 個 cluster 沒有提供 targets（不知道要修改哪個本地檔案），"
            "已略過自動修復；如需自動套用，請在語言對照表的 cluster 裡補上 targets。"
        )

    plan_only = not targets
    if plan_only:
        suggested_actions = [
            "語言對照表沒有任何 cluster 產出可自動套用的變更（可能是缺少 targets、"
            "找不到對應檔案、頁面含樣板語法，或找不到 <head> 標籤）。",
            "請檢查上方警告訊息，補齊語言對照表的 targets 或改用手動插入。",
        ]
        for cluster in hreflang_map.clusters:
            tag_htmls = render_hreflang_tags(cluster.alternates)
            suggested_actions.append(
                f"cluster {cluster.cluster_id!r} 應插入的標籤：" + " ".join(tag_htmls)
            )
        return PatchPlan(
            plan_id=f"hreflang-html-{_GENERATED_FINDING_ID}",
            finding_id=_GENERATED_FINDING_ID,
            fix_type="hreflang_generate_html",
            risk_level="medium",
            targets=[],
            summary="沒有任何頁面可以自動套用 hreflang 標籤，已產出建議步驟。",
            validation_steps=[],
            warnings=warnings,
            plan_only=True,
            suggested_actions=suggested_actions,
        )

    return PatchPlan(
        plan_id=f"hreflang-html-{_GENERATED_FINDING_ID}",
        finding_id=_GENERATED_FINDING_ID,
        fix_type="hreflang_generate_html",
        risk_level="medium",
        targets=targets,
        summary=(
            f"依使用者提供的語言對照表，為 {len(targets)} 個頁面插入/整組替換 hreflang 標籤。"
            "語言對照表視為權威輸入，工具不會驗證其業務正確性（例如網址是否真的對應正確語言版本）。"
        ),
        validation_steps=["重新爬取受影響頁面，確認 hreflang 標籤與語言對照表一致，且每組互相對稱"],
        warnings=warnings,
    )
