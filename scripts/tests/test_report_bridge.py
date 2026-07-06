"""顧問報告 → 內容 brief 串接的測試，重點在「不把技術問題誤轉成寫作任務」。"""

import pytest

from seo_advisor.models import Finding, Mode, Report, ReportTarget, Severity
from seo_advisor.writers.report_bridge import (
    NoContentOpportunityError,
    build_content_request_from_report,
    extract_content_opportunities,
)


def _finding(fid, category, title, rec, severity=Severity.P2, urls=None):
    return Finding(
        id=fid,
        title=title,
        mode=Mode.CONSULTANT,
        category=category,
        severity=severity,
        impact=3,
        effort=2,
        confidence=0.9,
        affected_urls=urls or [],
        recommendation=rec,
    )


def _report(findings, score=70.0):
    return Report(
        report_id="R1",
        generated_at="2026-07-06T00:00:00Z",
        target=ReportTarget(source_type="http", identifier="https://example.com"),
        mode=Mode.CONSULTANT,
        executive_summary="test",
        site_health_score=score,
        findings=findings,
    )


def test_content_quality_finding_becomes_opportunity():
    r = _report([
        _finding("F1", "content_quality", "頁面缺少 meta description",
                 "為每個頁面補上獨特的 meta 描述與標題", urls=["/a"]),
    ])
    opps = extract_content_opportunities(r)
    assert len(opps) == 1
    assert opps[0].target_url == "/a"


def test_technical_findings_excluded():
    """4xx / canonical / noindex / security 等技術問題不該轉成寫作任務。"""
    r = _report([
        _finding("F1", "indexability", "10 個頁面回傳 4xx", "修正連結或伺服器設定"),
        _finding("F2", "indexability", "canonical 指向不同網域", "改回指向本站"),
        _finding("F3", "security", "缺少 HTTPS", "全站啟用 HTTPS"),
    ])
    assert extract_content_opportunities(r) == []


def test_no_opportunity_without_topic_raises():
    r = _report([_finding("F1", "security", "缺 HTTPS", "啟用 HTTPS")])
    with pytest.raises(NoContentOpportunityError):
        build_content_request_from_report(r)


def test_no_opportunity_with_topic_still_builds():
    r = _report([_finding("F1", "security", "缺 HTTPS", "啟用 HTTPS")])
    req = build_content_request_from_report(r, topic_override="我的自訂主題")
    assert req.topic == "我的自訂主題"
    assert "報告未發現明確內容缺口" in req.source_notes


def test_topic_override_wins_over_extracted():
    r = _report([
        _finding("F1", "content_quality", "內容太薄", "擴充內容深度、增加字數", urls=["/a"]),
    ])
    req = build_content_request_from_report(r, topic_override="使用者指定")
    assert req.topic == "使用者指定"
    # 但 source_notes 仍帶入報告缺口
    assert "SEO 缺口" in req.source_notes or "SEO 問題" in req.source_notes


def test_internal_linking_produces_link_opportunity():
    r = _report([
        _finding("F1", "internal_linking", "發現孤兒頁", "為這些頁面補內容並建立內部連結",
                 urls=["/orphan1", "/orphan2"]),
    ])
    opps = extract_content_opportunities(r)
    assert opps[0].opportunity_type == "internal_linking"
    assert opps[0].internal_links


def test_higher_severity_ranks_first():
    r = _report([
        _finding("F1", "content_quality", "meta 描述重複", "改寫描述", severity=Severity.P3, urls=["/a"]),
        _finding("F2", "content_quality", "缺少 H1 標題", "補上 H1 標題", severity=Severity.P1, urls=["/b"]),
    ])
    opps = extract_content_opportunities(r)
    assert opps[0].related_finding_ids == ["F2"]  # P1 排最前


def test_metadata_batch_instructs_no_long_article():
    """多頁重複 metadata → 批次任務，source_notes 必須明確要求不寫長文。"""
    r = _report([
        _finding("F1", "content_quality", "多頁 meta description 重複",
                 "為每頁補上獨特的 meta 描述與標題", urls=["/a", "/b", "/c"]),
    ])
    req = build_content_request_from_report(r)
    assert "不要寫一篇文章" in req.source_notes


def test_p3_only_marked_low_priority():
    r = _report([
        _finding("F1", "content_quality", "meta 描述可再優化", "微調描述用字",
                 severity=Severity.P3, urls=["/a"]),
    ])
    req = build_content_request_from_report(r)
    assert "低優先" in req.source_notes


def test_local_path_marked_in_topic():
    r = _report([
        _finding("F1", "content_quality", "缺 H1", "補上 H1 標題與內容", urls=["/index.html"]),
    ])
    req = build_content_request_from_report(r)
    assert "本地路徑" in req.topic


def test_source_notes_contains_health_score():
    r = _report([
        _finding("F1", "content_quality", "內容太薄", "擴充內容", urls=["/a"]),
    ], score=42.0)
    req = build_content_request_from_report(r)
    assert "42/100" in req.source_notes
