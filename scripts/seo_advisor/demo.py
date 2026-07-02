"""Demo 模式：讓還沒有自己網站、或還不敢掃描真實網站的新手，先看一次完整報告長相。

使用內建的示範網站資產（seo_advisor/demo_assets/bad_site），該站台刻意包含
多種常見 SEO 問題，適合用來展示報告的完整樣貌。輸出前會明確告知使用者這是
示範資料，不是真實掃描結果。

這份資產放在套件內（seo_advisor/demo_assets/），而不是 scripts/tests/fixtures/，
是因為後者只在原始碼/editable install 情境下存在——正式打包成 wheel 散布時，
測試檔案通常不會被包進去，會導致 `seo-advisor demo` 在使用者端找不到檔案而
失效。透過 importlib.resources 存取套件內資產，無論是 editable install、
wheel 安裝或 zip-import，都能正確運作。
"""

from __future__ import annotations

import importlib.resources
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from seo_advisor.scan_runner import ProgressCallback, ScanOutcome, run_consultant_scan

_DEMO_ASSET_PACKAGE = "seo_advisor.demo_assets"
_DEMO_SITE_NAME = "bad_site"


@contextmanager
def _demo_site_path() -> Iterator[Path]:
    """取得示範網站資產在檔案系統上的實際路徑。

    `importlib.resources.as_file()` 會在資產被打包成 zip（zip-import）時
    自動解壓到暫存目錄，並在離開 context 後清理；一般安裝情況下則直接回傳
    套件內的實際路徑，不會有額外的複製開銷。
    """
    traversable = importlib.resources.files(_DEMO_ASSET_PACKAGE) / _DEMO_SITE_NAME
    with importlib.resources.as_file(traversable) as path:
        yield path


def run_demo_scan(*, out_dir: str, on_progress: ProgressCallback = lambda _: None) -> ScanOutcome:
    on_progress("使用內建示範網站資料（不是真實掃描）")
    try:
        with _demo_site_path() as demo_site_dir:
            if not demo_site_dir.exists():
                raise FileNotFoundError(
                    f"找不到內建的示範網站資料：{demo_site_dir}。"
                    "這通常代表安裝不完整，請重新下載或重新安裝專案。"
                )
            return run_consultant_scan(
                url=None,
                source=str(demo_site_dir),
                out_dir=out_dir,
                on_progress=on_progress,
            )
    except ModuleNotFoundError as exc:
        raise FileNotFoundError(
            f"找不到內建的示範網站資料套件（{_DEMO_ASSET_PACKAGE}）。"
            "這通常代表安裝不完整，請重新下載或重新安裝專案。"
        ) from exc
