"""CWV（Core Web Vitals）靜態線索的修復：只有 `decoding="async"` 是真正
會寫入的自動修復，其餘（img 缺尺寸、過多 blocking script）只產出
plan_only=True 的建議。

對應 analyzers/technical.py 的 `_check_cwv_static_hints` 產出的兩種
Finding（image_missing_dimensions_hint / blocking_scripts_hint）。

`decoding="async"` 是這批唯一自動套用的修復，因為它是低風險、語意明確的
屬性補充：只對完全沒有 `decoding` 屬性的 `<img>` 補上，不覆蓋任何既有值
（`sync`/`auto`/或開發者自訂的值可能是刻意設定），不影響版面配置或 JS
執行順序。

刻意不自動處理的部分：
- img 缺 width/height：這裡只查 HTML 屬性是否存在，不讀取圖片檔案驗證
  真實尺寸，自動填入錯誤的數值可能造成比不填更糟的版面跳動；且部分頁面
  刻意用 CSS aspect-ratio 保留版面空間而不寫 width/height 是合理設計，
  貿然自動補值有破壞既有設計的風險。
- 過多 blocking script：是否適合加 defer/async 需視該 script 的執行
  順序需求而定（例如某些腳本必須在特定時機同步執行），自動加上可能
  改變執行順序造成功能異常，因此只產出建議，不自動修改。
"""

from __future__ import annotations

import difflib
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from seo_advisor.fixers.models import FixTarget, NotFixableError, PatchPlan, ensure_write_target_allowed
from seo_advisor.models import Finding

# 單頁若要修改的 <img> 數量超過這個門檻，改為 plan_only 建議而非自動套用：
# 大量修改會產生難以 review 的巨大 diff，也可能暴露 BeautifulSoup 重新
# 序列化整份 HTML 造成的非預期格式變動，寧可交給人工批次處理。
_MAX_IMAGES_PER_PAGE_FOR_AUTO_FIX = 50


def _to_relative_path(url: str) -> str:
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
    return "IMAGE_MISSING_DIMENSIONS_HINT" in finding.id or "BLOCKING_SCRIPTS_HINT" in finding.id


def plan_fix(finding: Finding, *, pages: dict[str, str] | None = None) -> PatchPlan:
    """`image_missing_dimensions_hint`：自動補 `decoding="async"`（真寫入，
    需要 `pages` 提供受影響頁面的目前 HTML 內容）。

    `blocking_scripts_hint`：只產出 plan_only=True 的建議，不需要 `pages`。
    """
    if "BLOCKING_SCRIPTS_HINT" in finding.id:
        return _plan_blocking_scripts_suggestion(finding)
    return _plan_decoding_async_fix(finding, pages=pages or {})


def _plan_blocking_scripts_suggestion(finding: Finding) -> PatchPlan:
    return PatchPlan(
        plan_id=f"fix-{finding.id}",
        finding_id=finding.id,
        fix_type="cwv_blocking_scripts",
        risk_level="medium",
        targets=[],
        summary=(
            f"{finding.title}。是否適合為這些 <script> 加上 defer/async 需視個別"
            "腳本的執行順序需求而定，自動修改可能改變執行順序造成功能異常，"
            "因此只產出建議，不會自動套用。"
        ),
        validation_steps=["套用建議後重新執行掃描，確認 blocking script 數量已下降"],
        warnings=["這是建議方案，不是可自動套用的修復計畫；請先確認腳本執行順序需求。"],
        plan_only=True,
        suggested_actions=[
            "檢視受影響頁面裡的 <script src=\"...\"> 標籤，逐一評估是否可以加上 "
            'defer（延後到 HTML 解析完成後依原順序執行）或 async（下載完成後'
            "立即執行，不保證順序）。",
            "若腳本之間有依賴順序（例如先載入 jQuery 才能執行依賴它的腳本），"
            "改用 defer（會保持文件順序執行）比 async 更安全。",
            "套用後請實際在瀏覽器測試頁面功能是否正常，確認沒有因為執行時機"
            "改變而出錯。",
        ],
    )


def _plan_decoding_async_fix(finding: Finding, *, pages: dict[str, str]) -> PatchPlan:
    targets: list[FixTarget] = []
    warnings: list[str] = []
    oversized_pages: list[tuple[str, int]] = []

    for url in finding.affected_urls:
        rel_path = _to_relative_path(url)
        original = pages.get(url) or pages.get(rel_path)
        if original is None:
            warnings.append(f"找不到 {url} 的內容，已略過此頁面。")
            continue

        soup = BeautifulSoup(original, "lxml")
        images = soup.find_all("img")
        # 只補完全沒有 decoding 屬性的 <img>，不覆蓋任何既有值（sync/auto/
        # 其他自訂值可能是開發者刻意設定）。
        missing_decoding_count = sum(1 for img in images if img.get("decoding") is None)
        if missing_decoding_count == 0:
            continue

        if missing_decoding_count > _MAX_IMAGES_PER_PAGE_FOR_AUTO_FIX:
            oversized_pages.append((url, missing_decoding_count))
            continue

        ensure_write_target_allowed(rel_path)
        for img in images:
            if img.get("decoding") is None:
                img["decoding"] = "async"

        fixed = str(soup)
        targets.append(
            FixTarget(
                path=rel_path,
                original_content=original,
                fixed_content=fixed,
                diff_preview=_diff(rel_path, original, fixed),
            )
        )

    if oversized_pages:
        # 有任何一個頁面的修改量超過門檻：整份計畫改為 plan_only，避免
        # 「部分頁面自動套用、部分頁面要人工處理」這種混合狀態讓使用者
        # 困惑；已經算好的 targets 一併捨棄，只保留建議文字。
        suggested_actions = [
            f"{url} 有 {count} 個 <img> 缺少 decoding 屬性（超過自動套用門檻 "
            f"{_MAX_IMAGES_PER_PAGE_FOR_AUTO_FIX} 個），建議人工批次處理或分批"
            "縮小範圍後再自動套用。"
            for url, count in oversized_pages
        ]
        suggested_actions.append(
            '為每個 <img> 補上 decoding="async"（不要覆蓋已有 decoding 屬性的標籤），'
            "讓瀏覽器可以非同步解碼圖片、不阻塞主執行緒渲染。"
        )
        return PatchPlan(
            plan_id=f"fix-{finding.id}",
            finding_id=finding.id,
            fix_type="cwv_decoding_async",
            risk_level="medium",
            targets=[],
            summary=(
                f"{finding.title}。其中 {len(oversized_pages)} 個頁面單頁缺少 decoding "
                f"屬性的 <img> 數量超過 {_MAX_IMAGES_PER_PAGE_FOR_AUTO_FIX} 個，一次性"
                "自動修改會產生難以 review 的巨大 diff，因此改為建議方案，不自動套用。"
            ),
            validation_steps=["套用建議後重新爬取受影響頁面，確認 decoding 屬性已補上"],
            warnings=warnings,
            plan_only=True,
            suggested_actions=suggested_actions,
        )

    if not targets:
        raise NotFixableError(
            f"{finding.id} 沒有找到可修復的頁面內容（可能所有 <img> 都已經有 decoding 屬性）。"
        )

    return PatchPlan(
        plan_id=f"fix-{finding.id}",
        finding_id=finding.id,
        fix_type="cwv_decoding_async",
        risk_level="low",
        targets=targets,
        summary=(
            f"為 {len(targets)} 個頁面裡缺少 decoding 屬性的 <img> 補上 "
            'decoding="async"，讓瀏覽器可以非同步解碼圖片，不阻塞主執行緒渲染。'
            "這不會影響圖片版面大小，也不會覆蓋任何既有的 decoding 設定。"
        ),
        validation_steps=["重新爬取受影響頁面，確認 <img> 已補上 decoding=\"async\"（且未覆蓋既有值）"],
        warnings=warnings,
    )
