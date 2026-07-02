import zipfile
from pathlib import Path

import pytest

from seo_advisor.security.safe_archive import (
    UnsafeArchiveError,
    resolve_inside_root,
    safe_extract_zip,
)


def _make_zip(zip_path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def test_safe_extract_normal_zip_works(tmp_path):
    zip_path = tmp_path / "site.zip"
    _make_zip(zip_path, {"index.html": b"<h1>hi</h1>", "about.html": b"<h1>about</h1>"})
    extract_dir = tmp_path / "extracted"

    safe_extract_zip(zip_path, extract_dir)

    assert (extract_dir / "index.html").read_bytes() == b"<h1>hi</h1>"
    assert (extract_dir / "about.html").read_bytes() == b"<h1>about</h1>"


def test_safe_extract_rejects_path_traversal(tmp_path):
    zip_path = tmp_path / "evil.zip"
    _make_zip(zip_path, {"../../evil.txt": b"pwned"})
    extract_dir = tmp_path / "extracted"

    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(zip_path, extract_dir)

    # 確認沒有任何檔案被寫到 extract_dir 之外
    assert not (tmp_path / "evil.txt").exists()


def test_safe_extract_rejects_absolute_path(tmp_path):
    zip_path = tmp_path / "evil.zip"
    _make_zip(zip_path, {"/etc/evil.txt": b"pwned"})
    extract_dir = tmp_path / "extracted"

    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(zip_path, extract_dir)


def test_safe_extract_rejects_windows_drive_path(tmp_path):
    zip_path = tmp_path / "evil.zip"
    _make_zip(zip_path, {"C:\\Windows\\evil.txt": b"pwned"})
    extract_dir = tmp_path / "extracted"

    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(zip_path, extract_dir)


def test_safe_extract_rejects_too_many_files(tmp_path):
    zip_path = tmp_path / "many.zip"
    entries = {f"file{i}.txt": b"x" for i in range(10)}
    _make_zip(zip_path, entries)
    extract_dir = tmp_path / "extracted"

    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(zip_path, extract_dir, max_files=5)


def test_safe_extract_rejects_oversized_single_file(tmp_path):
    zip_path = tmp_path / "big.zip"
    _make_zip(zip_path, {"big.txt": b"x" * 1000})
    extract_dir = tmp_path / "extracted"

    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(zip_path, extract_dir, max_single_file_bytes=100)


def test_safe_extract_rejects_oversized_total(tmp_path):
    zip_path = tmp_path / "total.zip"
    _make_zip(zip_path, {"a.txt": b"x" * 100, "b.txt": b"x" * 100})
    extract_dir = tmp_path / "extracted"

    with pytest.raises(UnsafeArchiveError):
        safe_extract_zip(zip_path, extract_dir, max_total_uncompressed_bytes=150)


def test_resolve_inside_root_allows_normal_relative_path(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / "index.html").write_text("hi")

    resolved = resolve_inside_root(root, "/index.html")
    assert resolved == (root / "index.html").resolve()


def test_resolve_inside_root_rejects_traversal(tmp_path):
    root = tmp_path / "site"
    root.mkdir()

    with pytest.raises(UnsafeArchiveError):
        resolve_inside_root(root, "../../etc/passwd")


def test_resolve_inside_root_rejects_absolute_escape(tmp_path):
    root = tmp_path / "site"
    root.mkdir()

    with pytest.raises(UnsafeArchiveError):
        resolve_inside_root(root, "/../../etc/passwd")
