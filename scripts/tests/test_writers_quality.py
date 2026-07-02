from seo_advisor.writers.quality import (
    check_low_quality_openers,
    check_single_h1,
    check_ymyl_keywords,
    count_verification_markers,
    run_structural_checks,
)


def test_check_single_h1_passes_with_exactly_one():
    assert check_single_h1("# 標題\n\n內容") is None


def test_check_single_h1_flags_missing_h1():
    issue = check_single_h1("內容沒有標題")
    assert issue is not None
    assert issue.severity == "P1"


def test_check_single_h1_flags_multiple_h1():
    issue = check_single_h1("# 標題一\n\n# 標題二")
    assert issue is not None
    assert issue.severity == "P2"


def test_check_low_quality_openers_detects_cliche():
    issue = check_low_quality_openers("在當今快速變化的世界中，SEO 越來越重要。")
    assert issue is not None


def test_check_low_quality_openers_passes_direct_writing():
    issue = check_low_quality_openers("SEO 顧問服務通常包含三個核心項目。")
    assert issue is None


def test_check_ymyl_keywords_detects_medical_content():
    issue = check_ymyl_keywords("這篇文章討論如何診斷與治療常見疾病。")
    assert issue is not None
    assert issue.category == "trust"


def test_check_ymyl_keywords_passes_unrelated_content():
    issue = check_ymyl_keywords("這篇文章討論如何挑選 SEO 顧問服務。")
    assert issue is None


def test_count_verification_markers():
    text = "數據顯示 [需要查證: 來源不明] 成長了 50%，另一個 [需要查證: 待確認] 的說法。"
    assert count_verification_markers(text) == 2


def test_run_structural_checks_returns_empty_for_clean_draft():
    clean_draft = "# 如何挑選 SEO 顧問\n\nSEO 顧問服務通常包含三個核心項目。"
    assert run_structural_checks(clean_draft) == []


def test_run_structural_checks_flags_multiple_issues():
    bad_draft = (
        "# 標題一\n\n"
        "在當今快速變化的世界中，投資與醫療產業都需要 SEO。\n\n"
        "# 標題二"
    )
    issues = run_structural_checks(bad_draft)
    categories = {issue.category for issue in issues}
    assert "structure" in categories
    assert "content_quality" in categories
    assert "trust" in categories
