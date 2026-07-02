"""驗證正式打包成 wheel 後，demo 模式與 scoring 設定仍能被正確載入。

這個測試直接對應兩個已修復的真實 bug：
1. demo.py 原本讀取 scripts/tests/fixtures/bad_site，但測試檔案通常不會
   被打包進 wheel，導致使用者用 `pip install open-seo-advisor`（而非
   editable install）後，`seo-advisor demo` 會找不到示範資料而失敗。
2. scoring.py 原本會讀取專案根目錄的 config/scoring.yaml，同樣的路徑
   在正式安裝後不存在。

兩者都改成把資產複製一份放進 seo_advisor 套件內（demo_assets/、
config_assets/），這裡透過實際建置 wheel、解壓檢查內容物，確保這些
資產確實被包含在內，而不是只在 editable install 下看起來正常。

跑這個測試需要 `build` 套件；若環境沒有安裝，測試會自動跳過
（不阻擋一般開發流程，但建議在發布前手動執行一次確認）。
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent


def _has_build_module() -> bool:
    try:
        import build  # noqa: F401

        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _has_build_module(), reason="需要安裝 `build` 套件才能執行此測試")
def test_wheel_includes_bundled_assets(tmp_path):
    dist_dir = tmp_path / "dist"
    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(dist_dir)],
        cwd=str(_SCRIPTS_DIR),
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, f"wheel build 失敗：\n{result.stdout}\n{result.stderr}"

    wheel_files = list(dist_dir.glob("*.whl"))
    assert wheel_files, "沒有產生任何 .whl 檔案"

    with zipfile.ZipFile(wheel_files[0]) as zf:
        names = zf.namelist()

        demo_html_files = [n for n in names if "demo_assets" in n and n.endswith(".html")]
        assert demo_html_files, (
            f"wheel 內沒有找到 demo_assets 底下的 .html 檔案，"
            f"demo 模式在正式安裝後會失效。wheel 內容：{names}"
        )

        scoring_config_files = [
            n for n in names if "config_assets" in n and n.endswith("scoring.yaml")
        ]
        assert scoring_config_files, (
            f"wheel 內沒有找到 config_assets/scoring.yaml，"
            f"分類權重計算在正式安裝後會退回預設權重。wheel 內容：{names}"
        )
