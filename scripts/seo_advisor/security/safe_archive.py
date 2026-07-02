"""安全解壓 zip 檔案，防範 zip slip（path traversal）與 zip bomb。

背景：`zipfile.ZipFile.extractall()` 不會驗證壓縮檔內的路徑，惡意 zip 可以用
`../../../etc/passwd`、絕對路徑（`/etc/passwd`）或 Windows 磁碟機路徑
（`C:\\Windows\\System32\\...`）等條目名稱，讓解壓結果寫到目標目錄之外
（俗稱 zip slip）。使用者上傳的原始碼包正是這類攻擊最常見的載體，因此
LocalArchiveConnector 一律透過這裡的 `safe_extract_zip()` 解壓，不直接呼叫
`extractall()`。

同時防範 zip bomb：限制壓縮檔內檔案數量、單一檔案與總解壓大小上限。
"""

from __future__ import annotations

import zipfile
from pathlib import Path, PureWindowsPath

DEFAULT_MAX_FILES = 20_000
DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB
DEFAULT_MAX_SINGLE_FILE_BYTES = 512 * 1024 * 1024  # 512 MB


class UnsafeArchiveError(ValueError):
    """壓縮檔內容不安全（path traversal 或疑似 zip bomb）時拋出。"""


def _is_unsafe_member_name(name: str) -> bool:
    """偵測條目名稱是否包含 path traversal 或絕對路徑寫法。

    同時檢查 POSIX 與 Windows 風格的絕對路徑/磁碟機代號，因為 zip 檔案本身
    是跨平台格式，惡意產生的條目名稱不會受限於目前執行的作業系統。
    """
    if not name or name.strip() == "":
        return True
    normalized = name.replace("\\", "/")
    if normalized.startswith("/"):
        return True
    if PureWindowsPath(name).drive:
        return True
    parts = normalized.split("/")
    if ".." in parts:
        return True
    return False


def safe_extract_zip(
    zip_path: Path,
    extract_dir: Path,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_total_uncompressed_bytes: int = DEFAULT_MAX_TOTAL_UNCOMPRESSED_BYTES,
    max_single_file_bytes: int = DEFAULT_MAX_SINGLE_FILE_BYTES,
) -> None:
    """安全地把 zip 檔案解壓到 extract_dir，拒絕任何跳出目標目錄的條目。

    在寫入任何檔案之前，先完整驗證整個壓縮檔的清單（條目名稱、檔案數量、
    總大小），任何一項違規就整個中止、不寫入任何檔案，避免部分寫入造成
    難以排查的狀態。
    """
    extract_dir = extract_dir.resolve()
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        infolist = zf.infolist()

        if len(infolist) > max_files:
            raise UnsafeArchiveError(
                f"壓縮檔內檔案數量（{len(infolist)}）超過安全上限（{max_files}），"
                "為避免耗盡磁碟空間已拒絕解壓。"
            )

        total_uncompressed = 0
        resolved_targets: list[tuple[zipfile.ZipInfo, Path]] = []

        for member in infolist:
            if _is_unsafe_member_name(member.filename):
                raise UnsafeArchiveError(
                    f"壓縮檔內含有不安全的檔案路徑：{member.filename!r}，"
                    "可能是惡意構造的壓縮檔（path traversal），已拒絕解壓。"
                )

            if member.file_size > max_single_file_bytes:
                raise UnsafeArchiveError(
                    f"壓縮檔內的檔案 {member.filename!r} 大小（{member.file_size} bytes）"
                    f"超過單檔上限（{max_single_file_bytes} bytes），已拒絕解壓。"
                )

            total_uncompressed += member.file_size
            if total_uncompressed > max_total_uncompressed_bytes:
                raise UnsafeArchiveError(
                    "壓縮檔解壓後總大小超過安全上限，疑似 zip bomb，已拒絕解壓。"
                )

            target_path = (extract_dir / member.filename).resolve()
            if target_path != extract_dir and extract_dir not in target_path.parents:
                raise UnsafeArchiveError(
                    f"壓縮檔內的路徑 {member.filename!r} 會解壓到目標目錄之外，"
                    "已拒絕解壓。"
                )
            resolved_targets.append((member, target_path))

        for member, target_path in resolved_targets:
            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as source, open(target_path, "wb") as dest:
                _copy_with_limit(source, dest, max_single_file_bytes)


def _copy_with_limit(source, dest, max_bytes: int, chunk_size: int = 1024 * 1024) -> None:
    """邊讀邊寫並累計位元組數，防止壓縮比異常（decompression bomb）在寫入階段爆量。"""
    written = 0
    while True:
        chunk = source.read(chunk_size)
        if not chunk:
            break
        written += len(chunk)
        if written > max_bytes:
            raise UnsafeArchiveError("解壓過程中檔案大小超過安全上限，已中止並拒絕解壓。")
        dest.write(chunk)


def resolve_inside_root(root: Path, relative_path: str) -> Path:
    """把使用者提供的相對路徑解析到 root 之內，拒絕任何跳出 root 的存取。

    LocalArchiveConnector 的 fetch_url()/read_file()/list_files() 都必須透過
    這裡取得實際檔案路徑，避免 `../../../etc/passwd` 這類路徑穿越存取到
    root 目錄之外的檔案。
    """
    root = root.resolve()
    candidate = (root / relative_path.lstrip("/\\")).resolve()
    if candidate != root and root not in candidate.parents:
        raise UnsafeArchiveError(
            f"路徑 {relative_path!r} 會存取到掃描根目錄之外的位置，已拒絕存取。"
        )
    return candidate
