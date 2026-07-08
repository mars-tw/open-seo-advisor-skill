"""LocalArchiveConnector：掃描本地原始碼包（zip）或已解壓的專案目錄。

僅做檔案讀取與靜態 HTML 掃描，不執行專案內的任何程式（不 npm install、
不執行建置腳本），避免執行未知程式碼帶來的資安風險。
"""

from __future__ import annotations

import difflib
import hashlib
import os
import shutil
import tempfile
import time
from pathlib import Path

from seo_advisor.connectors.base import WebsiteConnector
from seo_advisor.encoding_utils import decode_html_bytes, detect_html_encoding
from seo_advisor.models import (
    BackupResult,
    ConnectorProfile,
    FileRecord,
    PageSnapshot,
    PatchResult,
    SafetyPolicy,
    UrlRecord,
)
from seo_advisor.security.safe_archive import resolve_inside_root, safe_extract_zip

# 備份與寫入能力預設不開放；只有明確把 write_files 加進 allowed_capabilities
# 的呼叫端（見 fixers/runner.py）才可能真的走到寫入路徑，且仍受 dry_run 約束。
_BACKUP_DIR_NAME = ".seo-advisor/backups"

# 單一本地檔案讀入記憶體的大小上限，避免超大檔案造成 OOM。
_MAX_LOCAL_FILE_BYTES = 25 * 1024 * 1024  # 25 MB


def _unified_diff_text(path: str, before: bytes, after: bytes) -> str:
    """把寫入前後的位元組內容用 UTF-8 解碼後產生 unified diff 文字，
    供 write_file() 的 dry-run 預覽使用。二進位/無法解碼的內容由呼叫端
    捕捉 UnicodeDecodeError 後改用略述文字。"""
    before_text = before.decode("utf-8")
    after_text = after.decode("utf-8")
    return "".join(
        difflib.unified_diff(
            before_text.splitlines(keepends=True),
            after_text.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )

_STACK_MARKERS = {
    "wordpress": ["wp-config.php", "wp-content"],
    "nextjs": ["next.config.js", "next.config.mjs", "next.config.ts"],
    "nuxt": ["nuxt.config.js", "nuxt.config.ts"],
    "laravel": ["artisan", "composer.json"],
    "static": ["index.html"],
}


class LocalArchiveConnector(WebsiteConnector):
    """讀取本地目錄或 zip 檔案，唯讀，不執行任何程式。"""

    def __init__(
        self,
        source_path: str,
        *,
        extract_to: str | None = None,
        policy: SafetyPolicy | None = None,
    ) -> None:
        self.policy = policy or SafetyPolicy(allowed_capabilities={"read_urls", "read_files"})

        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f"找不到路徑：{source_path}")

        if path.is_file() and path.suffix.lower() == ".zip":
            extract_dir = Path(extract_to) if extract_to else path.parent / f"{path.stem}_extracted"
            safe_extract_zip(path, extract_dir)
            self.root = extract_dir
        elif path.is_dir():
            self.root = path
        else:
            raise ValueError(f"不支援的來源類型（需為目錄或 .zip 檔）：{source_path}")

    def id(self) -> str:
        return f"local_archive:{self.root}"

    def capabilities(self) -> set[str]:
        """一律支援讀取；write_files/backup 只有在 SafetyPolicy 明確授權時才
        誠實回報，避免呼叫端誤以為唯讀模式的 connector 也能寫入。"""
        caps = {"read_urls", "read_files"}
        if "write_files" in self.policy.allowed_capabilities:
            caps.add("write_files")
        return caps

    def probe(self) -> ConnectorProfile:
        notes: list[str] = []
        detected_stack: str | None = None
        for stack, markers in _STACK_MARKERS.items():
            if any((self.root / marker).exists() for marker in markers):
                detected_stack = stack
                break

        def _exists_outside_backups(filename: str) -> bool:
            return any(
                not p.relative_to(self.root).as_posix().startswith(f"{_BACKUP_DIR_NAME}/")
                for p in self.root.rglob(filename)
            )

        has_robots = (self.root / "robots.txt").exists() or _exists_outside_backups("robots.txt")
        has_sitemap = (self.root / "sitemap.xml").exists() or _exists_outside_backups("sitemap.xml")

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
            if rel_path.startswith(f"{_BACKUP_DIR_NAME}/"):
                # Engineer Mode 自己的備份目錄不該被當成網站內容爬取/收進
                # sitemap，否則備份的舊版 HTML 會被誤判成真實頁面。
                continue
            records.append(UrlRecord(url=f"/{rel_path}", source="crawl", discovered_depth=0))
            if len(records) >= limit:
                break
        return records

    def fetch_url(self, url: str, *, render: bool = False, fetched_at: str = "") -> PageSnapshot:
        if render:
            raise NotImplementedError("本地原始碼包掃描不支援 render=True。")

        file_path = resolve_inside_root(self.root, url)
        if not file_path.exists():
            return PageSnapshot(
                url=url, status_code=404, final_url=url, headers={}, html="", fetched_at=fetched_at
            )

        # 大小上限：避免使用者的 repo/zip 內夾帶超大檔案讀進記憶體造成 OOM。
        if file_path.stat().st_size > _MAX_LOCAL_FILE_BYTES:
            return PageSnapshot(
                url=url,
                status_code=0,
                final_url=url,
                headers={},
                html="",
                fetched_at=fetched_at,
                fetch_error_type="file_too_large",
                fetch_error_message=(
                    f"檔案超過大小上限（{_MAX_LOCAL_FILE_BYTES // (1024 * 1024)} MB），已略過：{url}"
                ),
            )

        raw_bytes = file_path.read_bytes()
        html = decode_html_bytes(raw_bytes)
        return PageSnapshot(
            url=url,
            status_code=200,
            final_url=url,
            headers={},
            html=html,
            fetched_at=fetched_at,
            encoding=detect_html_encoding(raw_bytes),
        )

    def list_files(self, path: str) -> list[FileRecord]:
        target = resolve_inside_root(self.root, path) if path else self.root
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
        file_path = resolve_inside_root(self.root, path)
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"找不到檔案：{path}")
        if file_path.stat().st_size > _MAX_LOCAL_FILE_BYTES:
            raise ValueError(
                f"檔案超過大小上限（{_MAX_LOCAL_FILE_BYTES // (1024 * 1024)} MB），"
                f"為避免記憶體耗盡不予讀取：{path}"
            )
        return file_path.read_bytes()

    def backup(self, targets: list[str]) -> BackupResult:
        """把即將被修改的檔案複製到 `<root>/.seo-advisor/backups/<backup_id>/`，
        並寫入 manifest.json 記錄原始路徑與 sha256，供 rollback 比對「使用者
        是否事後又改過檔案」。備份是寫入前的必要步驟，備份失敗必須讓呼叫端
        看到例外、不得靜默略過。

        安全細節：
        - backup_id 用 mkdir(exist_ok=False) 確保不會靜默覆蓋既有備份（碰撞
          機率極低，但發生時必須是明確的錯誤而非悄悄混用兩次備份的內容）。
        - manifest 的 key 一律用 resolve_inside_root() 解析、重新算出的
          root-relative posix 路徑，而不是呼叫端傳入的原始字串，避免 target
          字串本身帶有奇怪片段（例如殘留的 ../）被直接當成檔案系統路徑片段
          寫入 backup_dir，確保備份目標同樣被限制在 backup_dir 之內。
        """
        self.policy.require_capability("write_files", connector_id=self.id())

        timestamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        backup_id = f"{timestamp}-{os.urandom(4).hex()}"
        backup_dir = self.root / _BACKUP_DIR_NAME / backup_id
        backup_dir.mkdir(parents=True, exist_ok=False)

        manifest: dict[str, dict] = {}
        backed_up: list[str] = []
        for raw_path in targets:
            src = resolve_inside_root(self.root, raw_path)
            rel_path = src.relative_to(self.root).as_posix()
            dest = resolve_inside_root(backup_dir / "files", rel_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src.exists():
                shutil.copy2(src, dest)
                content = src.read_bytes()
                manifest[rel_path] = {
                    "existed": True,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size": len(content),
                }
            else:
                # 檔案原本不存在（例如要新建 sitemap.xml）：manifest 記錄
                # existed=False，rollback 時代表應該刪除這個新增的檔案。
                manifest[rel_path] = {"existed": False, "sha256": None, "size": 0}
            backed_up.append(rel_path)

        import json

        (backup_dir / "manifest.json").write_text(
            json.dumps({"backup_id": backup_id, "root": str(self.root), "files": manifest},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return BackupResult(targets=backed_up, backup_path=str(backup_dir))

    def write_file(self, path: str, content: bytes, dry_run: bool = True) -> PatchResult:
        """寫入單一檔案。永遠 atomic write（寫 temp file 後 rename），寫入後
        重新讀檔驗證內容與 hash 一致，確保沒有半途損毀或寫入被截斷的情況。

        dry_run=True 時只回傳 diff 預覽，不觸碰檔案系統。
        """
        self.policy.require_capability("write_files", connector_id=self.id())

        target_path = resolve_inside_root(self.root, path)
        original = target_path.read_bytes() if target_path.exists() else b""
        try:
            diff_text = _unified_diff_text(path, original, content)
        except UnicodeDecodeError:
            diff_text = f"（二進位內容變更，共 {len(content)} bytes，略過文字 diff）"

        if dry_run:
            return PatchResult(path=path, dry_run=True, diff=diff_text, applied=False)

        self.policy.require_write(connector_id=self.id())

        target_path.parent.mkdir(parents=True, exist_ok=True)
        # 用 tempfile.mkstemp 而非手動拼接 "{pid}" 這類檔名：mkstemp 保證用
        # O_EXCL 語意原子建立一個保證不存在的檔名，避免同程序內平行處理多個
        # target（或極端情況下 pid 重用）造成的臨時檔命名碰撞。
        fd, tmp_name = tempfile.mkstemp(
            dir=str(target_path.parent), prefix=f".{target_path.name}.", suffix=".tmp"
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, target_path)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

        # 寫入後立即重新讀取驗證，確保寫入內容與預期完全一致。
        written = target_path.read_bytes()
        if hashlib.sha256(written).hexdigest() != hashlib.sha256(content).hexdigest():
            raise OSError(
                f"寫入後驗證失敗：{path} 的內容與預期不符，檔案可能已損毀，"
                "請立即從備份還原。"
            )

        return PatchResult(path=path, dry_run=False, diff=diff_text, applied=True)
