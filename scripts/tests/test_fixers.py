"""Engineer Mode fixers 測試：robots/sitemap/canonical 的 plan_fix，以及
runner 的 build_plan → apply_plan → rollback 端到端流程。"""

import pytest

from seo_advisor.connectors.local_archive import LocalArchiveConnector
from seo_advisor.crawler import CrawlResult
from seo_advisor.fixers import rollback as rollback_module
from seo_advisor.fixers import runner
from seo_advisor.fixers.models import NotFixableError, UnsafeWriteTargetError, ensure_write_target_allowed
from seo_advisor.fixers.safety import build_apply_confirmation, verify_confirmation
from seo_advisor.models import Finding, Mode, PageSnapshot, SafetyPolicy, Severity


def _finding(finding_id: str, affected_urls=None) -> Finding:
    # category 故意都用真實分析器會產出的粗略分組值（"indexability"），而不是
    # 用 finding_id 裡的細分類別字串，避免測試 fixture 巧合對齊 can_fix() 的
    # 判斷邏輯、掩蓋掉「can_fix 誤用 category 而非 id」這類真實 bug
    # （這正是先前手動測試才發現的問題：真實 Finding.category 一律是
    # "indexability"，細分類別只存在於 id 裡）。
    return Finding(
        id=finding_id,
        title="test finding",
        mode=Mode.CONSULTANT,
        category="indexability",
        severity=Severity.P2,
        impact=3,
        effort=1,
        confidence=0.9,
        affected_urls=affected_urls or [],
        evidence={},
        recommendation="test",
        validation=[],
        owner=Mode.ENGINEER,
    )


def _write_connector(root: str) -> LocalArchiveConnector:
    return LocalArchiveConnector(
        root, policy=SafetyPolicy(dry_run=False, allowed_capabilities={"read_urls", "read_files", "write_files"})
    )


# --- ensure_write_target_allowed ---


def test_ensure_write_target_allowed_rejects_python_files():
    with pytest.raises(UnsafeWriteTargetError):
        ensure_write_target_allowed("app.py")


def test_ensure_write_target_allowed_rejects_env_file():
    with pytest.raises(UnsafeWriteTargetError):
        ensure_write_target_allowed(".env")


def test_ensure_write_target_allowed_accepts_robots_txt():
    ensure_write_target_allowed("robots.txt")  # 不拋例外即通過


# --- robots.txt fixer ---


def test_robots_missing_creates_new_file_with_sitemap(tmp_path):
    finding = _finding("SEO-ROBOTS_MISSING-001")
    connector = _write_connector(str(tmp_path))
    crawl_result = CrawlResult()

    plan = runner.build_plan(finding, connector=connector, crawl_result=crawl_result, seed_url="https://example.com")
    assert plan.fix_type == "robots_txt"
    fixed = plan.targets[0].fixed_content
    assert "Sitemap: https://example.com/sitemap.xml" in fixed
    # 完全缺失時必須包含 User-agent/Allow，不能只有 sitemap 這行（那是
    # robots_no_sitemap 分支的行為，兩者不該混淆——見 canonical.py 同類 bug）。
    assert "User-agent: *" in fixed
    assert "Allow: /" in fixed
    assert plan.warnings  # 應提醒使用者原本沒有 robots.txt，需自行補 Disallow


def test_robots_no_sitemap_preserves_existing_rules(tmp_path):
    (tmp_path / "robots.txt").write_text("User-agent: *\nDisallow: /admin/\n", encoding="utf-8")
    finding = _finding("SEO-ROBOTS_NO_SITEMAP-001")
    connector = _write_connector(str(tmp_path))
    crawl_result = CrawlResult()

    plan = runner.build_plan(finding, connector=connector, crawl_result=crawl_result, seed_url="https://example.com")
    fixed = plan.targets[0].fixed_content
    assert "Disallow: /admin/" in fixed
    assert "Sitemap: https://example.com/sitemap.xml" in fixed


# --- sitemap fixer ---


def test_sitemap_missing_builds_urlset_from_crawled_pages(tmp_path):
    finding = _finding("SEO-SITEMAP_MISSING-001")
    connector = _write_connector(str(tmp_path))
    crawl_result = CrawlResult(
        pages={
            "https://example.com/": PageSnapshot(
                url="https://example.com/", status_code=200, final_url="https://example.com/",
                headers={}, html="<html></html>", fetched_at="2026-01-01T00:00:00Z",
            ),
            "https://example.com/noindex-page": PageSnapshot(
                url="https://example.com/noindex-page", status_code=200,
                final_url="https://example.com/noindex-page",
                headers={"x-robots-tag": "noindex"}, html="<html></html>", fetched_at="2026-01-01T00:00:00Z",
            ),
        }
    )

    plan = runner.build_plan(finding, connector=connector, crawl_result=crawl_result, seed_url="https://example.com")
    fixed = plan.targets[0].fixed_content
    assert "https://example.com/" in fixed
    assert "noindex-page" not in fixed  # noindex 頁面不該被收進 sitemap


def test_sitemap_missing_resolves_relative_paths_to_absolute_when_site_url_given(tmp_path):
    """本地掃描的 CrawlResult.pages key 通常是相對路徑（例如 /index.html），
    提供 --site-url（傳給 build_plan 的 seed_url）時，sitemap 內容應該是
    絕對 URL，而不是把相對路徑原封不動寫進 <loc>。"""
    finding = _finding("SEO-SITEMAP_MISSING-001")
    connector = _write_connector(str(tmp_path))
    crawl_result = CrawlResult(
        pages={
            "/index.html": PageSnapshot(
                url="/index.html", status_code=200, final_url="",
                headers={}, html="<html></html>", fetched_at="2026-01-01T00:00:00Z",
            ),
        }
    )

    plan = runner.build_plan(
        finding, connector=connector, crawl_result=crawl_result, seed_url="https://example.com"
    )
    fixed = plan.targets[0].fixed_content
    assert "https://example.com/index.html" in fixed


# --- canonical fixer ---


def test_canonical_conflict_removes_extra_tags(tmp_path):
    html = (
        '<html><head><link rel="canonical" href="https://example.com/a">'
        '<link rel="canonical" href="https://example.com/b"></head><body></body></html>'
    )
    finding = _finding("SEO-CANONICAL_CONFLICT-001", affected_urls=["https://example.com/a"])
    connector = _write_connector(str(tmp_path))
    crawl_result = CrawlResult(
        pages={
            "https://example.com/a": PageSnapshot(
                url="https://example.com/a", status_code=200, final_url="https://example.com/a",
                headers={}, html=html, fetched_at="2026-01-01T00:00:00Z",
            ),
        }
    )

    plan = runner.build_plan(finding, connector=connector, crawl_result=crawl_result, seed_url="https://example.com")
    fixed = plan.targets[0].fixed_content
    assert fixed.count("rel=\"canonical\"") == 1


def test_canonical_conflict_raises_when_no_matching_page():
    finding = _finding("SEO-CANONICAL_CONFLICT-001", affected_urls=["https://example.com/missing"])
    from seo_advisor.fixers import canonical

    with pytest.raises(NotFixableError):
        canonical.plan_fix(finding, pages={})


def test_canonical_conflict_skips_pages_with_template_syntax():
    """含有 Jinja/Django 等樣板語法的頁面不該被自動重新序列化（風險：
    屬性順序/格式被 BeautifulSoup 改寫，難以讓使用者一眼確認 diff 安全），
    應該略過並警告，而不是靜默改寫。"""
    from seo_advisor.fixers import canonical

    html = (
        '<html><head><link rel="canonical" href="{{ page.url }}">'
        '<link rel="canonical" href="https://example.com/dup"></head>'
        "<body>{% block content %}{% endblock %}</body></html>"
    )
    finding = _finding("SEO-CANONICAL_CONFLICT-001", affected_urls=["https://example.com/a"])

    with pytest.raises(NotFixableError):
        canonical.plan_fix(finding, pages={"https://example.com/a": html})


# --- runner.find_fixer / list_fixable_findings ---


def test_list_fixable_findings_filters_unsupported():
    findings = [
        _finding("SEO-ROBOTS_MISSING-001"),
        _finding("SEO-H1_MISSING-001"),  # 沒有對應 fixer
    ]
    fixable = runner.list_fixable_findings(findings)
    assert len(fixable) == 1
    assert fixable[0].id == "SEO-ROBOTS_MISSING-001"


# --- 端到端：build_plan -> apply_plan -> rollback ---


def test_apply_plan_then_rollback_restores_original_content(tmp_path):
    (tmp_path / "robots.txt").write_text("User-agent: *\n", encoding="utf-8")
    finding = _finding("SEO-ROBOTS_NO_SITEMAP-001")
    connector = _write_connector(str(tmp_path))
    crawl_result = CrawlResult()

    plan = runner.build_plan(finding, connector=connector, crawl_result=crawl_result, seed_url="https://example.com")
    assert verify_confirmation(build_apply_confirmation(plan.plan_id), build_apply_confirmation(plan.plan_id))

    result = runner.apply_plan(plan, connector=connector)
    assert result.applied is True
    assert "Sitemap:" in (tmp_path / "robots.txt").read_text(encoding="utf-8")

    rb = rollback_module.rollback(result.backup_id, root=tmp_path)
    assert rb.restored is True
    assert (tmp_path / "robots.txt").read_text(encoding="utf-8") == "User-agent: *\n"


def test_rollback_skips_file_manually_edited_after_apply(tmp_path):
    """使用者在 Engineer Mode 套用修復之後，又手動編輯了同一個檔案；
    rollback 必須跳過它，不能蓋掉使用者的新改動。"""
    (tmp_path / "robots.txt").write_text("User-agent: *\n", encoding="utf-8")
    finding = _finding("SEO-ROBOTS_NO_SITEMAP-001")
    connector = _write_connector(str(tmp_path))
    crawl_result = CrawlResult()

    plan = runner.build_plan(finding, connector=connector, crawl_result=crawl_result, seed_url="https://example.com")
    result = runner.apply_plan(plan, connector=connector)
    assert result.applied is True

    # 使用者事後手動編輯了這個檔案
    (tmp_path / "robots.txt").write_text("User-agent: *\nDisallow: /secret/\n", encoding="utf-8")

    rb = rollback_module.rollback(result.backup_id, root=tmp_path)
    assert rb.restored is False
    assert "robots.txt" in rb.skipped_paths
    assert (tmp_path / "robots.txt").read_text(encoding="utf-8") == "User-agent: *\nDisallow: /secret/\n"


def test_rollback_deletes_newly_created_file(tmp_path):
    """sitemap.xml 原本不存在，Engineer Mode 新建它；rollback 應該把這個
    新建檔案刪除，恢復到「原本沒有這個檔案」的狀態（而非留下空檔案）。"""
    finding = _finding("SEO-SITEMAP_MISSING-001")
    connector = _write_connector(str(tmp_path))
    crawl_result = CrawlResult()

    plan = runner.build_plan(finding, connector=connector, crawl_result=crawl_result, seed_url="https://example.com")
    result = runner.apply_plan(plan, connector=connector)
    assert result.applied is True
    assert (tmp_path / "sitemap.xml").exists()

    rb = rollback_module.rollback(result.backup_id, root=tmp_path)
    assert rb.restored is True
    assert not (tmp_path / "sitemap.xml").exists()


def test_rollback_does_not_delete_newly_created_file_if_user_edited_it(tmp_path):
    """使用者在 Engineer Mode 新建 sitemap.xml 之後，又手動編輯了內容；
    rollback 不該把使用者編輯過的新檔案刪掉。"""
    finding = _finding("SEO-SITEMAP_MISSING-001")
    connector = _write_connector(str(tmp_path))
    crawl_result = CrawlResult()

    plan = runner.build_plan(finding, connector=connector, crawl_result=crawl_result, seed_url="https://example.com")
    result = runner.apply_plan(plan, connector=connector)
    assert result.applied is True

    (tmp_path / "sitemap.xml").write_text("<urlset><!-- 使用者手動加的內容 --></urlset>", encoding="utf-8")

    rb = rollback_module.rollback(result.backup_id, root=tmp_path)
    assert rb.restored is False
    assert "sitemap.xml" in rb.skipped_paths
    assert (tmp_path / "sitemap.xml").exists()


def test_partial_apply_failure_still_allows_rollback_of_succeeded_files(tmp_path, monkeypatch):
    """多檔案套用時，若中途某個檔案寫入失敗，已成功寫入的檔案仍應能被
    正確 rollback（不能因為整批套用沒有「全部完成」就讓 applied-manifest
    留白，導致已寫入的部分也無法回滾）。"""
    html = (
        '<html><head><link rel="canonical" href="https://example.com/a">'
        '<link rel="canonical" href="https://example.com/b"></head><body></body></html>'
    )
    (tmp_path / "a.html").write_text(html, encoding="utf-8")
    (tmp_path / "b.html").write_text(html, encoding="utf-8")

    finding = _finding(
        "SEO-CANONICAL_CONFLICT-001",
        affected_urls=["https://example.com/a", "https://example.com/b"],
    )
    connector = _write_connector(str(tmp_path))
    crawl_result = CrawlResult(
        pages={
            "https://example.com/a": PageSnapshot(
                url="https://example.com/a", status_code=200, final_url="https://example.com/a",
                headers={}, html=html, fetched_at="2026-01-01T00:00:00Z",
            ),
            "https://example.com/b": PageSnapshot(
                url="https://example.com/b", status_code=200, final_url="https://example.com/b",
                headers={}, html=html, fetched_at="2026-01-01T00:00:00Z",
            ),
        }
    )

    plan = runner.build_plan(finding, connector=connector, crawl_result=crawl_result, seed_url="https://example.com")
    assert len(plan.targets) == 2

    original_write_file = connector.write_file
    call_count = {"n": 0}

    def flaky_write_file(path, content, dry_run=True):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise OSError("模擬第二個檔案寫入失敗（例如磁碟空間不足）")
        return original_write_file(path, content, dry_run=dry_run)

    monkeypatch.setattr(connector, "write_file", flaky_write_file)

    result = runner.apply_plan(plan, connector=connector)
    assert result.applied is False
    assert len(result.written_paths) == 1  # 第一個檔案成功、第二個中斷

    # 關鍵斷言：第一個已成功寫入的檔案，仍然可以被正確 rollback。
    rb = rollback_module.rollback(result.backup_id, root=tmp_path)
    assert result.written_paths[0] in rb.restored_paths
    restored_content = (tmp_path / result.written_paths[0]).read_text(encoding="utf-8")
    assert restored_content.count('rel="canonical"') == 2  # 恢復成原本的雙重 canonical


def test_rollback_without_applied_manifest_skips_everything(tmp_path):
    """備份存在但從未真的套用過（沒有 applied-manifest.json）時，保守跳過全部，
    不猜測是否安全還原。"""
    (tmp_path / "robots.txt").write_text("User-agent: *\n", encoding="utf-8")
    connector = _write_connector(str(tmp_path))
    backup_result = connector.backup(["robots.txt"])

    rb = rollback_module.rollback(backup_result.backup_path, root=tmp_path)
    assert rb.restored is False
    assert "robots.txt" in rb.skipped_paths
