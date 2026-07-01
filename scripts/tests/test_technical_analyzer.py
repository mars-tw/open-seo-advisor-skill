from pathlib import Path

from seo_advisor.analyzers.technical import analyze_technical_seo
from seo_advisor.connectors.local_archive import LocalArchiveConnector
from seo_advisor.crawler import crawl_site

FIXTURES = Path(__file__).parent / "fixtures"


def _crawl(site_dir: str):
    connector = LocalArchiveConnector(str(FIXTURES / site_dir))
    result = crawl_site(connector, seed_url="/index.html", max_urls=50, max_depth=3)
    return result


def test_good_site_has_no_metadata_findings():
    result = _crawl("good_site")
    findings = analyze_technical_seo(result, seed_url="/index.html")
    # 良好站台不應該有 title/meta/h1/canonical 相關的問題
    metadata_finding_ids = [f.id for f in findings if "TITLE" in f.id or "H1" in f.id or "CANONICAL" in f.id]
    assert metadata_finding_ids == []


def test_bad_site_flags_missing_title_and_h1_and_canonical_conflict():
    result = _crawl("bad_site")
    findings = analyze_technical_seo(result, seed_url="/index.html")
    finding_ids = {f.id for f in findings}

    assert any("TITLE_MISSING" in fid for fid in finding_ids)
    assert any("H1_MISSING" in fid for fid in finding_ids)
    assert any("CANONICAL_CONFLICT" in fid for fid in finding_ids)
    assert any("META_DESCRIPTION_MISSING" in fid for fid in finding_ids)


def test_all_findings_have_required_fields():
    result = _crawl("bad_site")
    findings = analyze_technical_seo(result, seed_url="/index.html")
    for finding in findings:
        assert finding.id
        assert finding.recommendation
        assert 1 <= finding.impact <= 5
        assert 1 <= finding.effort <= 5
        assert 0 <= finding.confidence <= 1


def test_single_page_site_not_flagged_as_orphan():
    # bad_site 只有一個頁面，不應該把唯一的入口頁誤判為孤兒頁
    result = _crawl("bad_site")
    findings = analyze_technical_seo(result, seed_url="/index.html")
    finding_ids = {f.id for f in findings}
    assert not any("ORPHAN" in fid for fid in finding_ids)
