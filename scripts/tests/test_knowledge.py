from seo_advisor.knowledge import get_domain, list_domains, load_methodology


def test_all_four_domains_loaded():
    domains = list_domains()
    assert set(domains) == {"ecommerce", "paid_ads_funnel", "content_brand", "growth_hacking"}


def test_each_domain_has_principles():
    for domain in load_methodology().values():
        assert domain.label
        assert len(domain.principles) >= 8
        for p in domain.principles:
            assert p.check and p.why


def test_get_domain_returns_none_for_unknown():
    assert get_domain("not-a-domain") is None


def test_each_domain_has_last_reviewed_date():
    """每個領域都該標記最後審查日期，讓貢獻者/使用者知道內容的時效性
    （見 docs/methodology.md 的免責聲明：內容可信度與時效性）。"""
    import re

    date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for domain_id, domain in load_methodology().items():
        assert domain.last_reviewed, f"{domain_id} 缺少 last_reviewed 欄位"
        assert date_pattern.match(domain.last_reviewed), (
            f"{domain_id} 的 last_reviewed 格式應為 YYYY-MM-DD，收到：{domain.last_reviewed}"
        )


def test_methodology_is_neutralized_no_expert_names():
    """合規紅線測試：知識庫不得含任何真實專家人名/課程名/商標。

    這條測試鎖住『中性化蒸餾』原則，讓 CI 持續守護——若未來有人不小心把
    具名內容加進知識庫，這裡會擋下來。
    """
    forbidden = [
        "ellen", "fishkin", "neil patel", "gary vee", "vaynerchuk",
        "brian dean", "backlinko", "moz", "ahrefs 課程", "老師的方法",
    ]
    blob = ""
    for domain in load_methodology().values():
        blob += domain.label.lower()
        for p in domain.principles:
            blob += p.check.lower() + p.why.lower()
    for name in forbidden:
        assert name not in blob, f"知識庫不應包含具名內容：{name}"
