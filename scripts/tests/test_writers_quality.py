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


def test_batch_qa_checks_visible_copy_not_the_industrial_url_or_json_fields():
    import json

    url = "/medical/heat-treatment.html"
    row = dict(url=url, title="Heat treatment of steel", h1="Surface treatment",
               meta_description="Dimensions for industrial buyers.")
    assert run_structural_checks(json.dumps([row]), [url]) == []
    row["meta_description"] = "Clinical treatment options for diabetes patients."
    assert any(i.category == "trust" for i in run_structural_checks(json.dumps([row]), [url]))


def test_shared_titles_are_not_a_required_rewrite_for_an_unrelated_batch():
    import json

    urls = ["/en-us/model", "/en-ca/model"]
    rows = [dict(url=u, title="Same Model", h1="Same Model", meta_description="Shop") for u in urls]
    assert run_structural_checks(json.dumps(rows), urls) == []


def test_context_terms_from_different_products_do_not_create_a_medical_claim():
    import json

    rows = [dict(url="/gears", title="Gear heat treatment", h1="Hardening",
                 meta_description="Compare alloy dimensions."),
            dict(url="/brackets", title="Patient monitor pole-mount bracket", h1="Adapter",
                 meta_description="Check hole spacing and bracket weight after surface treatment.")]
    assert run_structural_checks(json.dumps(rows), [r["url"] for r in rows]) == []


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
