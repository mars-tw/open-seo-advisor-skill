"""LocalArchiveConnector：掃描本地原始碼包（zip）或已解壓的專案目錄。

僅做檔案讀取與靜態 HTML 掃描，不執行專案內的任何程式（不 npm install、
不執行建置腳本），避免執行未知程式碼帶來的資安風險。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from seo_advisor.connectors.base import WebsiteConnector
from seo_advisor.models import ConnectorProfile, FileRecord, PageSnapshot, UrlRecord

_STACK_MARKERS = {
    "wordpress": ["wp-config.php", "wp-content"],
    "nextjs": ["next.config.js", "next.config.mjs", "next.config.ts"],
    "nuxt": ["nuxt.config.js", "nuxt.config.ts"],
    "laravel": ["artisan", "composer.json"],
    "static": ["index.html"],
}


class LocalArchiveConnector(WebsiteConnector):
    """讀取本地目錄或 zip 檔案，唯讀，不執行任何程式。"""

    def __init__(self, source_path: str, *, extract_to: str | None = None) -> None:
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"找不到路徑：{source_path}")

        if path.is_file() and path.suffix.lower() == ".zip":
            extract_dir = Path(extract_to) if extract_to else path.parent / f"{path.stem}_extracted"
            extract_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(path) as zf:
                zf.extractall(extract_dir)
            self.root = extract_dir
        elif path.is_dir():
            self.root = path
        else:
            raise ValueError(f"不支援的來源類型（需為目錄或 .zip 檔）：{source_path}")

    def id(self) -> str:
        return f"local_archive:{self.root}"

    def capabilities(self) -> set[str]:
        return {"read_urls", "read_files"}

    def probe(self) -> ConnectorProfile:
        notes: list[str] = []
        detected_stack: str | None = None
        for stack, markers in _STACK_MARKERS.items():
            if any((self.root / marker).exists() for marker in markers):
                detected_stack = stack
                break

        has_robots = (self.root / "robots.txt").exists() or any(
            self.root.rglob("robots.txt")
        )
        has_sitemap = (self.root / "sitemap.xml").exists() or any(
            self.root.rglob("sitemap.xml")
        )

        if detected_stack is None:
            notes.append("未偵測到已知技術棧標記，將以純靜態 HTML 掃描處理。")

        return ConnectorProfile(
            source_type="local_archive",
            detected_stack=detected_stack,
            has_sitemap=has_sitemap,
            has_robots_txt=has_robots,
            notes=notes,
        )

    def list_urls(self, seed: str, limit: int) -> list[UrlRecord]:
        records: list[UrlRecord] = []
        for html_file in self.root.rglob("*.html"):
            rel_path = html_file.relative_to(self.root).as_posix()
            records.append(UrlRecord(url=f"/{rel_path}", source="crawl", discovered_depth=0))
            if len(records) >= limit:
                break
        return records

    def fetch_url(self, url: str, render: bool = False, fetched_at: str = "") -> PageSnapshot:
        if render:
            raise NotImplementedError("本地原始碼包掃描不支援 render=True。")

        rel_path = url.lstrip("/")
        file_path = self.root / rel_path
        if not file_path.exists():
            return PageSnapshot(
                url=url, status_code=404, final_url=url, headers={}, html="", fetched_at=fetched_at
            )

        html = file_path.read_text(encoding="utf-8", errors="replace")
        return PageSnapshot(
            url=url,
            status_code=200,
            final_url=url,
            headers={},
            html=html,
            fetched_at=fetched_at,
        )

    def list_files(self, path: str) -> list[FileRecord]:
        target = self.root / path.lstrip("/") if path else self.root
        if not target.exists():
            return []
        records = []
        for entry in target.iterdir():
            records.append(
                FileRecord(
                    path=str(entry.relative_to(self.root).as_posix()),
                    size_bytes=entry.stat().st_size if entry.is_file() else 0,
                    is_dir=entry.is_dir(),
                )
            )
        return records

    def read_file(self, path: str) -> bytes:
        file_path = self.root / path.lstrip("/")
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"找不到檔案：{path}")
        return file_path.read_bytes()
