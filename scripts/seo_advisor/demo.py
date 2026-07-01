"""Demo 模式：讓還沒有自己網站、或還不敢掃描真實網站的新手，先看一次完整報告長相。

使用內建的測試 fixture（scripts/tests/fixtures/bad_site），該站台刻意包含多種
常見 SEO 問題，適合用來展示報告的完整樣貌。輸出前會明確告知使用者這是示範資料，
不是真實掃描結果。
"""

from __future__ import annotations

from pathlib import Path

from seo_advisor.scan_runner import ProgressCallback, ScanOutcome, run_consultant_scan

_DEMO_SITE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "bad_site"


def run_demo_scan(*, out_dir: str, on_progress: ProgressCallback = lambda _: None) -> ScanOutcome:
    if not _DEMO_SITE_DIR.exists():
        raise FileNotFoundError(
            f"找不到內建的示範網站資料：{_DEMO_SITE_DIR}。"
            "這通常代表安裝不完整，請重新下載或重新安裝專案。"
        )
    on_progress("使用內建示範網站資料（不是真實掃描）")
    return run_consultant_scan(
        url=None,
        source=str(_DEMO_SITE_DIR),
        out_dir=out_dir,
        on_progress=on_progress,
    )
