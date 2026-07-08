from pathlib import Path

from seo_advisor.connectors.local_archive import LocalArchiveConnector

FIXTURES = Path(__file__).parent / "fixtures"


def test_probe_detects_static_site():
    connector = LocalArchiveConnector(str(FIXTURES / "good_site"))
    profile = connector.probe()
    assert profile.source_type == "local_archive"
    assert profile.detected_stack == "static"


def test_list_urls_finds_html_files():
    connector = LocalArchiveConnector(str(FIXTURES / "good_site"))
    urls = connector.list_urls(seed="/", limit=10)
    paths = {u.url for u in urls}
    assert "/index.html" in paths
    assert "/about.html" in paths


def test_list_urls_excludes_engineer_mode_backup_directory(tmp_path):
    """Engineer Mode 的 .seo-advisor/backups/ 裡若有備份的 .html 檔案，
    不該被 list_urls 掃到，否則會被誤判成真實網站頁面（進而被誤收進
    sitemap fixer 產出的 sitemap.xml）。"""
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    backup_html = tmp_path / ".seo-advisor" / "backups" / "20260101-abcd" / "files" / "robots.html"
    backup_html.parent.mkdir(parents=True)
    backup_html.write_text("<html>backup copy</html>", encoding="utf-8")

    connector = LocalArchiveConnector(str(tmp_path))
    urls = {u.url for u in connector.list_urls(seed="/", limit=100)}
    assert "/index.html" in urls
    assert not any(".seo-advisor" in u for u in urls)


def test_fetch_url_reads_file_content():
    connector = LocalArchiveConnector(str(FIXTURES / "good_site"))
    snapshot = connector.fetch_url("/index.html")
    assert snapshot.status_code == 200
    assert "歡迎來到範例網站" in snapshot.html


def test_fetch_url_missing_file_returns_404():
    connector = LocalArchiveConnector(str(FIXTURES / "good_site"))
    snapshot = connector.fetch_url("/does-not-exist.html")
    assert snapshot.status_code == 404


def test_capabilities_are_read_only():
    connector = LocalArchiveConnector(str(FIXTURES / "good_site"))
    caps = connector.capabilities()
    assert "read_urls" in caps
    assert "read_files" in caps
    assert "write_files" not in caps
