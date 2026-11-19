"""LocalArchiveConnector：掃描本地原始碼包（zip）或已解壓的專案目錄。

僅做檔案讀取與靜態 HTML 掃描，不執行專案內的任何程式（不 npm install、
不執行建置腳本），避免執行未知程式碼帶來的資安風險。
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from seo_advisor.connectors.base import WebsiteConnector
from seo_advisor.connectors.text_response import file_snapshot_fields
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
from seo_advisor.sitemaps import MAX_BYTES, SitemapFetch, decode_sitemap_bytes
from seo_advisor.url_utils import http_origin, sitemap_url

# 備份與寫入能力預設不開放；只有明確把 write_files 加進 allowed_capabilities
# 的呼叫端（見 fixers/runner.py）才可能真的走到寫入路徑，且仍受 dry_run 約束。
_BACKUP_DIR_NAME = ".seo-advisor/backups"

# 工具/版控目錄：掃描網站內容時一律跳過，避免把版控中繼資料、依賴套件或
# 備份目錄誤判為真實網站頁面（進而被 sitemap fixer 誤收進 sitemap.xml，
# 或讓 probe() 的 has_robots/has_sitemap 偵測到誤導性的結果）。
_TOOLING_DIR_PREFIXES = (".git/", ".seo-advisor/", "node_modules/")


def _tracking_query_field(field: str) -> bool:
    key, _, value = field.partition("=")
    return (
        key.startswith("utm_")
        or key in {"gclid", "fbclid", "msclkid"}
        or (key == "ref" and value == "nav")
    )


def _requires_runtime(parts, file_path: Path) -> bool:
    return bool(
        parts.query
        or "%2F" in parts.path
        or "%5C" in parts.path
        or (file_path.suffix.lower() == ".php" and file_path.is_file())
        or (
            file_path.is_dir()
            and not (file_path / "index.html").is_file()
            and (file_path / "index.php").is_file()
        )
    )


def _is_inside_tooling_dir(rel_path: str) -> bool:
    return any(rel_path.startswith(prefix) for prefix in _TOOLING_DIR_PREFIXES)


def _is_generated_report(path: Path) -> bool:
    """Identify this tool's specific report file, including older custom output directories."""
    if path.name != "report.html" or not path.is_file():
        return False
    try:
        with path.open("rb") as stream:
            header = stream.read(131072)
        if b"<meta name=\"generator\" content=\"Open SEO Advisor Consultant\">" in header:
            return True
        if "<title>SEO 健檢報告：".encode() not in header:
            return False
        with path.with_name("report.json").open(encoding="utf-8") as stream:
            report = json.load(stream)
        return (
            isinstance(report, dict) and report.get("mode") == "consultant"
            and isinstance(report.get("report_id"), str)
            and ("<code>" + report["report_id"] + "</code>").encode() in header
        )
    except (ValueError, OSError):
        return False

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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def writable_archive_directory(archive: Path, *, require_existing: bool = False) -> Path:
    """Open an identified repair workspace without overwriting an existing directory."""
    digest = file_sha256(archive)
    marker = Path(".seo-advisor", "source-archive.sha256")
    dest = archive.with_name(archive.stem + "_extracted")
    alternative = archive.with_name(archive.stem + "_extracted_" + digest[:12])
    if (dest.exists() and not (dest / marker).is_file()) or (
        not dest.exists() and alternative.exists()
    ):
        dest = alternative
    if dest.exists():
        if not (dest / marker).is_file() or (dest / marker).read_text(encoding="ascii") != digest:
            raise ValueError(
                f"現有解壓目錄與 ZIP 來源無法核對。請檢查 {dest}，或直接指定該目錄重新預覽。"
            )
        return dest
    if require_existing:
        raise ValueError("找不到預覽時的解壓目錄，請重新預覽。")
    with tempfile.TemporaryDirectory(dir=archive.parent) as staging:
        root = Path(staging, "site")
        safe_extract_zip(archive, root)
        if file_sha256(archive) != digest:
            raise ValueError("ZIP 在解壓期間已變更，請使用穩定的版本重新預覽。")
        (root / marker).parent.mkdir(exist_ok=True)
        (root / marker).write_text(digest, encoding="ascii")
        try:
            root.rename(dest)
        except OSError:
            if (
                not (dest / marker).is_file()
                or (dest / marker).read_text(encoding="ascii") != digest
            ):
                raise
    return dest


class LocalArchiveConnector(WebsiteConnector):
    """讀取本地目錄或 zip 檔案，唯讀，不執行任何程式。"""

    def __init__(
        self,
        source_path: str,
        *,
        extract_to: str | None = None,
        policy: SafetyPolicy | None = None,
        site_url: str | None = None,
    ) -> None:
        self.policy = policy or SafetyPolicy(allowed_capabilities={"read_urls", "read_files"})
        self.site_origin = http_origin(site_url) if site_url else None
        self._temporary_archive = None

        path = Path(source_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"找不到路徑：{source_path}")

        if (
            path.is_file()
            and path.suffix.lower() == ".zip"
            and extract_to is None
            and "write_files" in self.policy.allowed_capabilities
        ):
            self.root = writable_archive_directory(path)
        elif path.is_file() and path.suffix.lower() == ".zip":
            if extract_to is None:
                self._temporary_archive = tempfile.TemporaryDirectory(prefix="seo-advisor-audit-")
                extract_dir = Path(self._temporary_archive.name)
            else:
                extract_dir = Path(extract_to).resolve()
                if extract_dir.exists() and any(extract_dir.iterdir()):
                    raise ValueError("明確指定的解壓目錄已有檔案。請選空目錄以保留現有內容。")
            try:
                safe_extract_zip(path, extract_dir)
            except BaseException:
                self.close()
                raise
            self.root = extract_dir
        elif path.is_dir():
            self.root = path
        else:
            raise ValueError(f"不支援的來源類型（需為目錄或 .zip 檔）：{source_path}")

        # 備份實際落地的根目錄：預設在 self.root 之內（.seo-advisor/backups），
        # 子類別（例如 GitRepoConnector）可以覆寫成 repo 之外的位置，避免備份
        # 產生的檔案讓 `git status` 誤判 working tree 不乾淨。
        self._backup_root = self.root

    def close(self) -> None:
        if self._temporary_archive is not None:
            self._temporary_archive.cleanup()
            self._temporary_archive = None

    def is_url_in_scope(self, url: str) -> bool:
        """Map only a confirmed origin and local documents to this archive."""
        parsed = urlsplit(url)
        if parsed.netloc or parsed.scheme:
            if not self.site_origin or parsed.scheme not in {"http", "https"}:
                return False
            if http_origin(url) != self.site_origin:
                return False
        local_path = unquote(parsed.path).lstrip("/")
        if _is_inside_tooling_dir(local_path):
            return False
        return not _is_generated_report(resolve_inside_root(self.root, local_path))

    def local_url(self, url: str) -> str:
        if not self.is_url_in_scope(url):
            raise ValueError("無法將此外部網址或工具產出檔對應到本機來源。")
        parsed = urlsplit(sitemap_url(url))
        path, query = parsed.path or "/", parsed.query
        # A percent-escaped slash has deployment-specific routing semantics. Keep its identity.
        if "%2F" not in path and "%5C" not in path:
            local = resolve_inside_root(self.root, unquote(path))
            if local.is_dir() and (local / "index.html").is_file():
                path = path.rstrip("/") + "/index.html"
                local = local / "index.html"
            if local.is_file():
                query = "&".join(
                    field for field in query.split("&") if not _tracking_query_field(field)
                )
        return urlunsplit(("", "", path, query, ""))

    def read_sitemap_file(self, url: str) -> SitemapFetch:
        parts = urlsplit(self.local_url(url))
        path = resolve_inside_root(self.root, unquote(parts.path))
        if _requires_runtime(parts, path):
            return SitemapFetch(0, error="需要網站伺服器提供實際 sitemap 內容", limited=True)
        if not path.is_file():
            return SitemapFetch(404)
        with path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return SitemapFetch(200, error="本機 sitemap 檔案超過 50 MiB 讀取上限", limited=True)
        return decode_sitemap_bytes(raw)

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

        def _exists_outside_tooling_dirs(filename: str) -> bool:
            return any(
                not _is_inside_tooling_dir(p.relative_to(self.root).as_posix())
                for p in self.root.rglob(filename)
            )

        has_robots = (self.root / "robots.txt").exists() or _exists_outside_tooling_dirs("robots.txt")
        has_sitemap = (self.root / "sitemap.xml").exists() or _exists_outside_tooling_dirs("sitemap.xml")

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
        for parent, directories, files in os.walk(self.root):
            directories[:] = sorted(name for name in directories if name + "/" not in _TOOLING_DIR_PREFIXES)
            for name in sorted(files):
                html_file = Path(parent, name)
                if html_file.suffix.lower() not in {".html", ".htm", ".xhtml"} or _is_generated_report(html_file):
                    continue
                rel_path = html_file.relative_to(self.root).as_posix()
                url = "/" + quote(rel_path, safe="/:@!$&'()*+,;=")
                records.append(UrlRecord(url=url, source="crawl", discovered_depth=0))
                if len(records) >= limit:
                    return records
        return records

    def fetch_url(self, url: str, *, render: bool = False, fetched_at: str = "") -> PageSnapshot:
        if render:
            raise NotImplementedError("本地原始碼包掃描不支援 render=True。")

        parts = urlsplit(self.local_url(url))
        file_path = resolve_inside_root(self.root, unquote(parts.path))
        if _requires_runtime(parts, file_path):
            return PageSnapshot(
                url=url,
                final_url=url,
                status_code=0,
                fetched_at=fetched_at,
                fetch_error_type="requires_runtime",
                fetch_error_message="這個網址需要由網站伺服器對應或執行，請以部署後的網址驗證。",
            )
        if file_path.is_dir():
            file_path = resolve_inside_root(self.root, (file_path / "index.html").relative_to(self.root.resolve()).as_posix())
        if not file_path.is_file():
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
        return PageSnapshot(
            url=url,
            status_code=200,
            final_url=url,
            fetched_at=fetched_at,
            **file_snapshot_fields(file_path.name, raw_bytes),
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
        """把即將被修改的檔案複製到 `<_backup_root>/.seo-advisor/backups/<backup_id>/`，
        並寫入 manifest.json 記錄原始路徑與 sha256，供 rollback 比對「使用者
        是否事後又改過檔案」。備份是寫入前的必要步驟，備份失敗必須讓呼叫端
        看到例外、不得靜默略過。

        _backup_root 預設等於 self.root（備份留在 repo/掃描目錄內）；
        GitRepoConnector 會覆寫成 repo 之外的路徑，避免備份檔案讓
        `git status` 誤判 working tree 不乾淨。

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
        backup_dir = self._backup_root / _BACKUP_DIR_NAME / backup_id
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
