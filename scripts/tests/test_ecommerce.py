import json

from seo_advisor.ecommerce.analyzer import analyze_listing
from seo_advisor.ecommerce.models import EcommerceListing
from seo_advisor.ecommerce.report import render_ecommerce_json, render_ecommerce_markdown


def _good_listing():
    return EcommerceListing(
        title="高續航無線降噪藍牙耳機 入耳式 運動防水 40 小時電量 附充電盒",
        bullet_points=[
            "主動降噪技術有效隔絕環境噪音，通勤與辦公更專注",
            "單次充電可用 10 小時，搭配充電盒總計 40 小時續航",
            "IPX5 防水設計，運動流汗或小雨都能安心使用",
            "人體工學入耳設計，長時間配戴不易疲勞",
            "藍牙 5.3 穩定連線，低延遲適合影音與遊戲",
        ],
        backend_keywords=["earbuds", "wireless headphones", "運動耳機", "降噪耳機", "藍牙耳機"],
        main_image_present=True,
        secondary_image_count=6,
        has_a_plus_content=True,
        review_count=320,
        rating=4.5,
        in_stock=True,
        has_buy_box=True,
        variations_count=3,
    )


def test_good_listing_scores_high():
    report = analyze_listing(_good_listing())
    assert report.listing_health_score >= 90


def test_out_of_stock_is_p0():
    listing = _good_listing()
    listing.in_stock = False
    report = analyze_listing(listing)
    assert any(f.severity.value == "P0" and f.category == "availability" for f in report.findings)


def test_low_rating_is_p1():
    listing = _good_listing()
    listing.rating = 3.5
    report = analyze_listing(listing)
    assert any(f.severity.value == "P1" and f.category == "reviews" for f in report.findings)


def test_missing_main_image_flagged():
    listing = _good_listing()
    listing.main_image_present = False
    report = analyze_listing(listing)
    assert any(f.category == "images" and f.severity.value == "P1" for f in report.findings)


def test_short_title_flagged():
    listing = _good_listing()
    listing.title = "耳機"
    report = analyze_listing(listing)
    assert any(f.category == "title" for f in report.findings)


def test_findings_reference_methodology_check():
    listing = _good_listing()
    listing.has_a_plus_content = False
    report = analyze_listing(listing)
    a_plus = next(f for f in report.findings if "A+" in f.title)
    assert a_plus.evidence.get("check")  # 引用了方法論檢核點


def test_report_includes_applied_checklist():
    report = analyze_listing(_good_listing())
    assert report.applied_checklist


def test_render_markdown_and_json(tmp_path):
    report = analyze_listing(_good_listing())
    md = render_ecommerce_markdown(report)
    assert "電商 Listing 健檢報告" in md
    data = json.loads(render_ecommerce_json(report))
    assert "listing_health_score" in data
