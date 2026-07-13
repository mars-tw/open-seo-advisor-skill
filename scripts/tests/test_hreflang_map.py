import pytest

from seo_advisor.fixers.hreflang_map import (
    InvalidLanguageMapError,
    parse_language_map,
    render_hreflang_tags,
)


def _valid_raw() -> dict:
    return {
        "clusters": [
            {
                "id": "home",
                "alternates": {
                    "zh-TW": "https://example.com/zh/",
                    "en": "https://example.com/en/",
                    "x-default": "https://example.com/",
                },
                "targets": {"zh-TW": "zh/index.html", "en": "en/index.html"},
            }
        ]
    }


class TestParseLanguageMap:
    def test_accepts_valid_map(self):
        hmap = parse_language_map(_valid_raw())
        assert len(hmap.clusters) == 1
        assert hmap.clusters[0].cluster_id == "home"

    def test_targets_defaults_to_empty(self):
        raw = _valid_raw()
        del raw["clusters"][0]["targets"]
        hmap = parse_language_map(raw)
        assert hmap.clusters[0].targets == {}

    def test_rejects_missing_clusters_key(self):
        with pytest.raises(InvalidLanguageMapError):
            parse_language_map({})

    def test_rejects_empty_clusters(self):
        with pytest.raises(InvalidLanguageMapError):
            parse_language_map({"clusters": []})

    def test_rejects_duplicate_cluster_id(self):
        raw = _valid_raw()
        raw["clusters"].append(dict(raw["clusters"][0]))
        with pytest.raises(InvalidLanguageMapError):
            parse_language_map(raw)

    def test_rejects_single_alternate(self):
        raw = _valid_raw()
        raw["clusters"][0]["alternates"] = {"en": "https://example.com/en/"}
        with pytest.raises(InvalidLanguageMapError):
            parse_language_map(raw)

    def test_rejects_invalid_language_code(self):
        raw = _valid_raw()
        raw["clusters"][0]["alternates"]["English"] = "https://example.com/en2/"
        with pytest.raises(InvalidLanguageMapError):
            parse_language_map(raw)

    def test_accepts_region_code(self):
        raw = {
            "clusters": [
                {
                    "id": "home",
                    "alternates": {"en-US": "https://example.com/us/", "en-GB": "https://example.com/gb/"},
                }
            ]
        }
        parse_language_map(raw)  # 不拋例外即通過

    def test_rejects_non_http_scheme(self):
        raw = _valid_raw()
        raw["clusters"][0]["alternates"]["en"] = "ftp://example.com/en/"
        with pytest.raises(InvalidLanguageMapError):
            parse_language_map(raw)

    def test_rejects_userinfo_in_url(self):
        raw = _valid_raw()
        raw["clusters"][0]["alternates"]["en"] = "https://user:pass@example.com/en/"
        with pytest.raises(InvalidLanguageMapError):
            parse_language_map(raw)

    def test_rejects_fragment_in_url(self):
        raw = _valid_raw()
        raw["clusters"][0]["alternates"]["en"] = "https://example.com/en/#section"
        with pytest.raises(InvalidLanguageMapError):
            parse_language_map(raw)

    def test_rejects_path_traversal_in_url(self):
        raw = _valid_raw()
        raw["clusters"][0]["alternates"]["en"] = "https://example.com/en/../admin"
        with pytest.raises(InvalidLanguageMapError):
            parse_language_map(raw)

    def test_rejects_url_reused_across_clusters_after_host_normalization(self):
        """host 大小寫或結尾點不同但本質是同一台主機/同一個網址時，
        也必須被偵測為重複，避免 Example.com / example.com. 繞過檢查。"""
        raw = _valid_raw()
        raw["clusters"].append(
            {
                "id": "about",
                "alternates": {
                    "zh-TW": "https://Example.com./zh/",  # 大小寫 + 結尾點，實際等於 home cluster 的 zh-TW URL
                    "en": "https://example.com/about/en/",
                },
            }
        )
        with pytest.raises(InvalidLanguageMapError):
            parse_language_map(raw)

    def test_rejects_url_reused_across_clusters(self):
        raw = _valid_raw()
        raw["clusters"].append(
            {
                "id": "about",
                "alternates": {
                    "zh-TW": "https://example.com/zh/",  # 跟 home cluster 重複
                    "en": "https://example.com/about/en/",
                },
            }
        )
        with pytest.raises(InvalidLanguageMapError):
            parse_language_map(raw)

    def test_rejects_target_for_undeclared_language(self):
        raw = _valid_raw()
        raw["clusters"][0]["targets"]["fr"] = "fr/index.html"
        with pytest.raises(InvalidLanguageMapError):
            parse_language_map(raw)

    def test_rejects_non_dict_cluster(self):
        with pytest.raises(InvalidLanguageMapError):
            parse_language_map({"clusters": ["not-a-dict"]})

    def test_rejects_missing_id(self):
        raw = _valid_raw()
        del raw["clusters"][0]["id"]
        with pytest.raises(InvalidLanguageMapError):
            parse_language_map(raw)


class TestRenderHreflangTags:
    def test_orders_alphabetically_with_x_default_last(self):
        tags = render_hreflang_tags(
            {"x-default": "https://example.com/", "en": "https://example.com/en/", "zh-TW": "https://example.com/zh/"}
        )
        assert [t for t in tags] == [
            '<link rel="alternate" hreflang="en" href="https://example.com/en/"/>',
            '<link rel="alternate" hreflang="zh-TW" href="https://example.com/zh/"/>',
            '<link rel="alternate" hreflang="x-default" href="https://example.com/"/>',
        ]

    def test_escapes_ampersand_in_url_attribute(self):
        """quoteattr 遇到值本身含雙引號時會自動改用單引號包裹屬性值
        （XML 屬性值合法轉義的兩種等效寫法之一），這裡只斷言核心的
        跨標籤注入防護：& 必須被轉義，不能讓屬性值提前結束。"""
        tags = render_hreflang_tags({"en": 'https://example.com/en/?a=1&b=2'})
        assert "&amp;" in tags[0]
        assert "&b=2" not in tags[0]  # 未轉義的裸 & 不應該出現
