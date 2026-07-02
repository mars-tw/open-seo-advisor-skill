"""技術面 SEO 分析：把 CrawlResult 轉換成 Finding 清單。

檢查項目對應 docs/modes.md 的 Consultant Mode 已實作清單：
- HTTP 狀態碼分布、redirect chain
- robots.txt 存在性與是否誤擋重要資源
- sitemap.xml 存在性與格式
- canonical 一致性
- title / meta description / H1 完整性與重複率
- 孤兒頁偵測
- noindex 使用狀況
- HTTPS 使用狀況
"""

from __future__ import annotations

from collections import Counter
from urllib.parse import urlparse
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from seo_advisor.crawler import CrawlResult, find_orphan_pages
from seo_advisor.models import Finding, Mode, Severity

_MAX_URLS_PER_SITEMAP_FILE = 50_000


def _make_id(category: str, seq: int) -> str:
    return f"SEO-{category.upper()}-{seq:03d}"


def analyze_technical_seo(result: CrawlResult, *, seed_url: str) -> list[Finding]:
    findings: list[Finding] = []
    seq_counter: Counter[str] = Counter()

    def next_id(category: str) -> str:
        seq_counter[category] += 1
        return _make_id(category, seq_counter[category])

    findings.extend(_check_status_codes(result, next_id))
    findings.extend(_check_redirect_chains(result, next_id))
    findings.extend(_check_robots_txt(result, next_id))
    findings.extend(_check_sitemap(result, next_id))
    findings.extend(_check_https(result, seed_url, next_id))
    findings.extend(_check_page_metadata(result, next_id))
    findings.extend(_check_noindex(result, next_id))
    findings.extend(_check_orphan_pages(result, seed_url, next_id))

    return findings


def _check_status_codes(result: CrawlResult, next_id) -> list[Finding]:
    findings: list[Finding] = []
    error_urls = [url for url, snap in result.pages.items() if snap.status_code >= 400]
    zero_status_urls = [url for url, snap in result.pages.items() if snap.status_code == 0]

    if error_urls:
        findings.append(
            Finding(
                id=next_id("http_errors"),
                title=f"發現 {len(error_urls)} 個頁面回傳 4xx/5xx 錯誤",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P1 if len(error_urls) > 5 else Severity.P2,
                impact=4 if len(error_urls) > 5 else 2,
                effort=2,
                confidence=1.0,
                affected_urls=error_urls[:50],
                evidence={"error_count": len(error_urls)},
                recommendation="逐一檢查這些 URL：確認是否應該回傳 200（修正連結或伺服器設定），"
                "或應該用 301 導向到正確頁面，或該頁面本來就該下架並回傳正確的 410。",
                validation=["重新爬取這些 URL，確認狀態碼已修正為預期值"],
                owner=Mode.ENGINEER,
                sources=["google-search-essentials"],
            )
        )

    if zero_status_urls:
        findings.append(
            Finding(
                id=next_id("fetch_failed"),
                title=f"{len(zero_status_urls)} 個頁面請求失敗（逾時或連線錯誤）",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P2,
                impact=2,
                effort=2,
                confidence=0.7,
                affected_urls=zero_status_urls[:50],
                evidence={"failed_count": len(zero_status_urls)},
                recommendation="確認這些 URL 是否可正常存取，排除暫時性網路問題後再次確認。",
                validation=["重新爬取確認是否仍然失敗"],
                owner=Mode.CONSULTANT,
            )
        )

    return findings


def _check_redirect_chains(result: CrawlResult, next_id) -> list[Finding]:
    findings: list[Finding] = []
    long_chains = {
        url: snap.redirect_chain
        for url, snap in result.pages.items()
        if len(snap.redirect_chain) >= 2
    }
    if long_chains:
        findings.append(
            Finding(
                id=next_id("redirect_chain"),
                title=f"發現 {len(long_chains)} 個頁面存在多層重導鏈",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P2,
                impact=3,
                effort=2,
                confidence=0.9,
                affected_urls=list(long_chains.keys())[:50],
                evidence={"example_chain": next(iter(long_chains.values()))},
                recommendation="將多層重導縮短為單一 301 直接導向最終目標，減少爬取預算浪費與"
                "頁面載入延遲。",
                validation=["重新爬取確認重導鏈已縮短為 1 層"],
                owner=Mode.ENGINEER,
                sources=["google-search-essentials"],
            )
        )
    return findings


def _check_robots_txt(result: CrawlResult, next_id) -> list[Finding]:
    findings: list[Finding] = []
    if result.robots_txt is None:
        findings.append(
            Finding(
                id=next_id("robots_missing"),
                title="網站沒有 robots.txt",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P3,
                impact=2,
                effort=1,
                confidence=0.8,
                affected_urls=["/robots.txt"],
                evidence={},
                recommendation="建立 robots.txt 並宣告 sitemap 位置，即使目前沒有需要阻擋的路徑，"
                "也建議明確宣告以避免爬蟲行為的不確定性。",
                validation=["確認 /robots.txt 回傳 200 且格式正確"],
                owner=Mode.ENGINEER,
                sources=["robots-txt-intro"],
            )
        )
    elif "sitemap:" not in result.robots_txt.lower():
        findings.append(
            Finding(
                id=next_id("robots_no_sitemap"),
                title="robots.txt 未宣告 sitemap 位置",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P3,
                impact=1,
                effort=1,
                confidence=0.9,
                affected_urls=["/robots.txt"],
                evidence={},
                recommendation="在 robots.txt 中加入 `Sitemap: https://<domain>/sitemap.xml`，"
                "協助搜尋引擎更快發現網站的完整 URL 清單。",
                validation=["確認 robots.txt 內容包含 Sitemap 宣告"],
                owner=Mode.ENGINEER,
                sources=["robots-txt-intro"],
            )
        )
    return findings


def _check_sitemap(result: CrawlResult, next_id) -> list[Finding]:
    findings: list[Finding] = []
    if result.sitemap_xml is None:
        findings.append(
            Finding(
                id=next_id("sitemap_missing"),
                title="網站沒有 sitemap.xml",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P2,
                impact=3,
                effort=2,
                confidence=0.8,
                affected_urls=["/sitemap.xml"],
                evidence={},
                recommendation="建立 sitemap.xml 並列出所有應被索引的正規 URL，協助搜尋引擎"
                "更完整地發現與索引網站內容。",
                validation=["確認 /sitemap.xml 回傳 200 且為合法 XML"],
                owner=Mode.ENGINEER,
                sources=["sitemaps-protocol"],
            )
        )
        return findings

    try:
        root = ElementTree.fromstring(result.sitemap_xml)
        url_count = len(list(root))
        if url_count > _MAX_URLS_PER_SITEMAP_FILE:
            findings.append(
                Finding(
                    id=next_id("sitemap_too_large"),
                    title=f"sitemap.xml 內 URL 數量（{url_count}）超過單檔上限 50,000",
                    mode=Mode.CONSULTANT,
                    category="indexability",
                    severity=Severity.P2,
                    impact=3,
                    effort=3,
                    confidence=1.0,
                    affected_urls=["/sitemap.xml"],
                    evidence={"url_count": url_count},
                    recommendation="改用 sitemap index 拆分成多個子 sitemap 檔案，每檔不超過"
                    "50,000 個 URL 或 50MB。",
                    validation=["確認拆分後的 sitemap index 結構正確"],
                    owner=Mode.ENGINEER,
                    sources=["sitemaps-protocol"],
                )
            )
    except ElementTree.ParseError:
        findings.append(
            Finding(
                id=next_id("sitemap_invalid_xml"),
                title="sitemap.xml 不是合法的 XML 格式",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P1,
                impact=4,
                effort=2,
                confidence=1.0,
                affected_urls=["/sitemap.xml"],
                evidence={},
                recommendation="修正 sitemap.xml 的 XML 格式錯誤，可用 XML validator 檢查。",
                validation=["確認 sitemap.xml 可被 XML parser 正確解析"],
                owner=Mode.ENGINEER,
                sources=["sitemaps-protocol"],
            )
        )

    return findings


def _check_https(result: CrawlResult, seed_url: str, next_id) -> list[Finding]:
    findings: list[Finding] = []
    http_pages = [
        url
        for url in result.pages
        if urlparse(url).scheme == "http"
    ]
    if http_pages and urlparse(seed_url).scheme == "http":
        findings.append(
            Finding(
                id=next_id("https_missing"),
                title="網站未強制使用 HTTPS",
                mode=Mode.CONSULTANT,
                category="security",
                severity=Severity.P1,
                impact=4,
                effort=3,
                confidence=0.9,
                affected_urls=http_pages[:20],
                evidence={"http_page_count": len(http_pages)},
                recommendation="為網站安裝 SSL/TLS 憑證並將所有 HTTP 請求以 301 導向至 HTTPS。",
                validation=["確認 http:// 開頭的請求會 301 導向到對應的 https:// URL"],
                owner=Mode.ENGINEER,
                sources=["owasp-tls-cheatsheet"],
            )
        )
    return findings


def _check_page_metadata(result: CrawlResult, next_id) -> list[Finding]:
    findings: list[Finding] = []
    missing_title: list[str] = []
    missing_meta_description: list[str] = []
    missing_h1: list[str] = []
    multiple_h1: list[str] = []
    title_to_urls: dict[str, list[str]] = {}
    canonical_conflicts: list[str] = []

    for url, snapshot in result.pages.items():
        if snapshot.status_code != 200 or not snapshot.html:
            continue

        soup = BeautifulSoup(snapshot.html, "lxml")

        title_tag = soup.find("title")
        title_text = title_tag.get_text(strip=True) if title_tag else ""
        if not title_text:
            missing_title.append(url)
        else:
            title_to_urls.setdefault(title_text, []).append(url)

        meta_desc = soup.find("meta", attrs={"name": "description"})
        if not meta_desc or not meta_desc.get("content", "").strip():
            missing_meta_description.append(url)

        h1_tags = soup.find_all("h1")
        if len(h1_tags) == 0:
            missing_h1.append(url)
        elif len(h1_tags) > 1:
            multiple_h1.append(url)

        canonical_tags = soup.find_all("link", rel="canonical")
        if len(canonical_tags) > 1:
            canonical_conflicts.append(url)

    if missing_title:
        findings.append(
            _metadata_finding(
                next_id("title_missing"),
                f"{len(missing_title)} 個頁面缺少 <title> 標籤",
                missing_title,
                impact=4,
                severity=Severity.P1,
                recommendation="為每個頁面撰寫獨特且能反映頁面內容的 <title>，長度建議在"
                "50-60 字元之間。",
            )
        )

    duplicate_title_groups = {
        text: urls for text, urls in title_to_urls.items() if len(urls) > 1
    }
    if duplicate_title_groups:
        affected = [url for urls in duplicate_title_groups.values() for url in urls]
        # evidence 只保留前幾組範例，避免重複標題組數量很多時報告過於冗長
        example_groups = dict(list(duplicate_title_groups.items())[:5])
        findings.append(
            Finding(
                id=next_id("title_duplicate"),
                title=f"發現 {len(duplicate_title_groups)} 組重複的 <title>",
                mode=Mode.CONSULTANT,
                category="content_quality",
                severity=Severity.P2,
                impact=3,
                effort=2,
                confidence=0.8,
                affected_urls=affected[:50],
                evidence={
                    "duplicate_title_groups": len(duplicate_title_groups),
                    "examples": example_groups,
                },
                recommendation="為每個頁面撰寫獨特的 title，避免不同頁面使用相同標題造成"
                "搜尋結果混淆與內部競爭。",
                validation=["重新爬取確認每個頁面的 title 皆為獨特"],
                owner=Mode.ENGINEER,
            )
        )

    if missing_meta_description:
        findings.append(
            _metadata_finding(
                next_id("meta_description_missing"),
                f"{len(missing_meta_description)} 個頁面缺少 meta description",
                missing_meta_description,
                impact=2,
                severity=Severity.P3,
                recommendation="為重要頁面撰寫獨特的 meta description，雖非直接排名因子，"
                "但影響搜尋結果的點擊率（CTR）。",
            )
        )

    if missing_h1:
        findings.append(
            _metadata_finding(
                next_id("h1_missing"),
                f"{len(missing_h1)} 個頁面缺少 <h1> 標籤",
                missing_h1,
                impact=3,
                severity=Severity.P2,
                recommendation="為每個頁面加上單一、能反映頁面主題的 <h1> 標籤。",
            )
        )

    if multiple_h1:
        findings.append(
            _metadata_finding(
                next_id("h1_multiple"),
                f"{len(multiple_h1)} 個頁面有多個 <h1> 標籤",
                multiple_h1,
                impact=1,
                severity=Severity.P3,
                recommendation="每個頁面建議只使用一個 <h1>，其餘標題階層使用 <h2>/<h3>。",
            )
        )

    if canonical_conflicts:
        findings.append(
            Finding(
                id=next_id("canonical_conflict"),
                title=f"{len(canonical_conflicts)} 個頁面有多個 canonical 標籤",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P1,
                impact=4,
                effort=2,
                confidence=1.0,
                affected_urls=canonical_conflicts[:50],
                evidence={},
                recommendation="每個頁面只能有一個 canonical 標籤，多重宣告會讓搜尋引擎"
                "自行選擇甚至忽略，需修正模板邏輯只輸出單一 canonical。",
                validation=["重新爬取確認每頁僅有一個 canonical 標籤"],
                owner=Mode.ENGINEER,
                sources=["canonicalization"],
            )
        )

    return findings


def _metadata_finding(
    finding_id: str,
    title: str,
    affected_urls: list[str],
    *,
    impact: int,
    severity: Severity,
    recommendation: str,
) -> Finding:
    return Finding(
        id=finding_id,
        title=title,
        mode=Mode.CONSULTANT,
        category="content_quality",
        severity=severity,
        impact=impact,
        effort=2,
        confidence=0.9,
        affected_urls=affected_urls[:50],
        evidence={"affected_count": len(affected_urls)},
        recommendation=recommendation,
        validation=["重新爬取確認問題已修正"],
        owner=Mode.ENGINEER,
        sources=["google-search-essentials"],
    )


def _check_noindex(result: CrawlResult, next_id) -> list[Finding]:
    """檢查頁面是否被 <meta name="robots" content="noindex"> 或 HTTP
    X-Robots-Tag 標頭阻擋索引。這類設定容易在模板誤植或 CMS 設定錯誤時
    意外套用到不該阻擋的重要頁面，且不像 robots.txt 那麼顯眼容易發現。
    """
    findings: list[Finding] = []
    noindex_urls: list[str] = []

    for url, snapshot in result.pages.items():
        if snapshot.status_code != 200:
            continue

        x_robots_tag = snapshot.headers.get("x-robots-tag", "")
        if "noindex" in x_robots_tag.lower():
            noindex_urls.append(url)
            continue

        if not snapshot.html:
            continue

        soup = BeautifulSoup(snapshot.html, "lxml")
        robots_meta = soup.find("meta", attrs={"name": "robots"})
        if robots_meta:
            content = robots_meta.get("content", "").lower()
            if "noindex" in content:
                noindex_urls.append(url)

    if noindex_urls:
        findings.append(
            Finding(
                id=next_id("noindex_present"),
                title=f"發現 {len(noindex_urls)} 個頁面被設定為 noindex（不會被搜尋引擎索引）",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P1,
                impact=4,
                effort=2,
                confidence=0.85,
                affected_urls=noindex_urls[:50],
                evidence={"noindex_count": len(noindex_urls)},
                recommendation="確認這些頁面是否應該被搜尋引擎索引。如果是重要頁面被誤植 "
                "noindex（常見於模板繼承錯誤或 CMS 設定疏漏），請移除 "
                "noindex 設定；如果本來就不該被索引，則此為預期行為。",
                validation=["重新爬取確認 noindex 設定符合預期"],
                owner=Mode.ENGINEER,
                sources=["google-search-essentials"],
            )
        )

    return findings


def _check_orphan_pages(result: CrawlResult, seed_url: str, next_id) -> list[Finding]:
    findings: list[Finding] = []
    orphans = find_orphan_pages(result, seed_url)
    if orphans:
        findings.append(
            Finding(
                id=next_id("orphan_pages"),
                title=f"發現 {len(orphans)} 個孤兒頁（沒有任何內部連結指向）",
                mode=Mode.CONSULTANT,
                category="internal_linking",
                severity=Severity.P2,
                impact=3,
                effort=2,
                confidence=0.7,
                affected_urls=orphans[:50],
                evidence={"orphan_count": len(orphans)},
                recommendation="為這些頁面建立來自相關頁面的內部連結，孤兒頁難以被搜尋引擎"
                "透過爬取發現，也無法從內部連結獲得權重傳遞。",
                validation=["重新爬取確認這些頁面已被其他頁面連結"],
                owner=Mode.CONSULTANT,
            )
        )
    return findings
