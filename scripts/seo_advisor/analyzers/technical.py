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

import json
from collections import Counter
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from seo_advisor.crawler import CrawlResult, document_base, find_orphan_pages
from seo_advisor.indexability import google_noindex, valid_hreflang
from seo_advisor.models import Finding, Mode, Severity
from seo_advisor.robots_rules import googlebot_blocks, robots_fields
from seo_advisor.sitemaps import parse_sitemap
from seo_advisor.url_utils import canonical_destination, normalize_host as _normalize_host


def _canonicalize_url_for_comparison(url: str) -> str:
    return canonical_destination("", url)


def _make_id(category: str, seq: int) -> str:
    return f"SEO-{category.upper()}-{seq:03d}"


# 明顯不需要社群分享卡片的路徑片段，缺 OG 不視為問題（降噪）。
_NON_SOCIAL_PATH_HINTS = ("/api/", "/admin/", "/wp-json/", "/wp-admin/", "/.well-known/")


def _parsed_pages(result: CrawlResult) -> dict[str, BeautifulSoup]:
    """把可分析的頁面（狀態碼 200 且有 HTML）各自解析一次，讓
    _check_page_metadata/_check_noindex/_check_canonical_target/
    _check_social_metadata/_check_structured_data 共用同一份 soup，
    避免同一頁 HTML 被 BeautifulSoup(lxml) 重複解析 5 次。
    """
    return {
        _canonicalize_url_for_comparison(snapshot.final_url or url): BeautifulSoup(
            snapshot.html, "lxml"
        )
        for url, snapshot in result.pages.items()
        if snapshot.status_code == 200 and snapshot.html
    }


def analyze_technical_seo(
    result: CrawlResult, *, seed_url: str, expect_indexing: bool = True
) -> list[Finding]:
    findings: list[Finding] = []
    seq_counter: Counter[str] = Counter()

    def next_id(category: str) -> str:
        seq_counter[category] += 1
        return _make_id(category, seq_counter[category])

    parsed = _parsed_pages(result)

    noindex = {}
    preview_directives = {}
    for url, snapshot in result.pages.items():
        final = _canonicalize_url_for_comparison(snapshot.final_url or url)
        if snapshot.status_code == 200:
            rules = google_noindex(parsed.get(final), snapshot.indexing_headers)
            if rules:
                noindex[final] = rules
            elif not expect_indexing and final in parsed:
                tags = parsed[final].find_all("meta", attrs={"name": True, "content": True})
                observed = [
                    f"meta {tag['name']}: {tag['content']}"
                    for tag in tags
                    if tag["name"].strip().casefold() in {"robots", "googlebot"}
                ]
                header_lines = snapshot.x_robots_fields or [
                    value
                    for key, value in snapshot.headers.items()
                    if key.casefold() == "x-robots-tag"
                ]
                preview_directives[final] = observed + [
                    f"X-Robots-Tag: {value}" for value in header_lines
                ]
    preview_excludes_all_pages = not expect_indexing and bool(parsed) and parsed.keys() <= noindex.keys()
    findings.extend(_check_status_codes(result, next_id))
    findings.extend(_check_redirect_chains(result, next_id))
    findings.extend(_check_robots_txt(result, next_id, require_sitemap=not preview_excludes_all_pages))
    findings.extend(_check_sitemap(result, next_id, require_urls=not preview_excludes_all_pages))
    findings.extend(_check_https(result, next_id))
    findings.extend(_check_page_metadata(parsed, next_id))
    excluded_from_link_advice = set(noindex)
    blocked_by_reader = {url for url, snap in result.pages.items()
                         if snap.fetch_error_type == "blocked_by_robots_txt"}
    if expect_indexing:
        findings.extend(_check_noindex(noindex, next_id))
        candidates = set(parsed) - set(noindex)
        candidates.update(blocked_by_reader & result.sitemap_page_urls)
        googlebot_findings = _check_googlebot_crawl(candidates, result.robots_txt, next_id)
        findings.extend(googlebot_findings)
        for finding in googlebot_findings:
            excluded_from_link_advice.update(finding.affected_urls)
    else:
        findings.extend(_check_googlebot_crawl(
            set(noindex) | blocked_by_reader, result.robots_txt, next_id, preview=True
        ))
    if not expect_indexing and (exposed := sorted(set(parsed) - set(noindex))):
        findings.append(
            Finding(
                id=next_id("preview_indexable"),
                title="預覽頁缺少針對 Google 的 noindex",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P1,
                impact=4,
                effort=1,
                confidence=1.0,
                affected_urls=exposed,
                evidence={
                    "html_without_noindex": len(exposed),
                    "observed_directives": {
                        url: preview_directives.get(url, []) for url in exposed
                    },
                },
                recommendation="確認預覽範圍，為不應出現在搜尋結果的預覽頁加入有效 noindex 或限制存取。",
                validation=["在預覽頁 HTML 或 HTTP 標頭中讀回 Google 適用的索引指令。"],
                owner=Mode.ENGINEER,
                sources=["google-search-essentials"],
            )
        )
    findings.extend(_check_canonical_target(parsed, result, noindex, next_id))
    findings.extend(_check_social_metadata(parsed, noindex, next_id))
    findings.extend(_check_structured_data(parsed, next_id))
    findings.extend(_check_orphan_pages(result, seed_url, next_id, excluded_from_link_advice))
    findings.extend(_check_hreflang(parsed, result, seed_url, next_id))
    findings.extend(_check_cwv_static_hints(parsed, next_id))

    return findings


def _check_status_codes(result: CrawlResult, next_id) -> list[Finding]:
    findings: list[Finding] = []
    error_urls = [url for url, snap in result.pages.items() if snap.status_code >= 400]
    errors_by_type: dict[str, list[str]] = {}
    for url, snap in result.pages.items():
        if snap.status_code == 0 and snap.fetch_error_type not in {"blocked_by_robots_txt", "requires_runtime"}:
            errors_by_type.setdefault(snap.fetch_error_type or "unknown", []).append(url)

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

    for kind, zero_status_urls in errors_by_type.items():
        error_label = "請求逾時" if kind == "timeout" else "未能取得內容"
        findings.append(
            Finding(
                id=next_id("fetch_failed"),
                title=f"{len(zero_status_urls)} 個網址{error_label}",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P2,
                impact=2,
                effort=2,
                confidence=0.7,
                affected_urls=zero_status_urls[:50],
                evidence={"failed_count": len(zero_status_urls), "type": kind},
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


def _check_robots_txt(result: CrawlResult, next_id, *, require_sitemap: bool = True) -> list[Finding]:
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
    elif require_sitemap and not any(
        key == "sitemap" and value for key, value in robots_fields(result.robots_txt)
    ):
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


def _check_googlebot_crawl(urls, content, next_id, *, preview=False):
    paths = {}
    for url in sorted(urls):
        parts = urlparse(url)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        paths.setdefault(path, []).append(url)
    blocked = googlebot_blocks(content or "", list(paths))
    if not blocked:
        return []
    return [
        Finding(
            id=next_id("preview_noindex_blocked" if preview else "googlebot_blocked"),
            title=("robots.txt 阻擋 Googlebot 讀取預覽頁的收錄指令" if preview
                   else "robots.txt 阻擋 Googlebot 抓取預定收錄頁面"),
            mode=Mode.CONSULTANT,
            category="indexability",
            severity=Severity.P1,
            impact=4,
            effort=2,
            confidence=1.0,
            affected_urls=[url for path in blocked for url in paths[path]],
            evidence={
                "rules": {
                    path: {"agent": agent, "disallow": rule}
                    for path, (agent, rule) in blocked.items()
                }
            },
            recommendation=("若依賴 noindex，讓 Googlebot 能抓取並讀到指令；需限制閱覽時使用登入或授權。"
                            if preview else "確認頁面用途，對預定收錄的頁面調整 Googlebot 實際命中的群組與路徑規則。"),
            validation=["對網站正式網址重新檢查 Googlebot 規則及 Search Console URL 檢查結果。"],
            owner=Mode.ENGINEER,
            sources=["robots-txt-intro"],
        )
    ]


def _check_sitemap(result: CrawlResult, next_id, *, require_urls: bool = True) -> list[Finding]:
    findings: list[Finding] = []
    documents = result.sitemap_documents
    if not documents and result.sitemap_xml is not None:
        documents = {"/sitemap.xml": result.sitemap_xml}
    if result.sitemap_errors:
        findings.append(
            Finding(
                id=next_id("sitemap_unreadable"),
                title="sitemap 未能完整讀取",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P2,
                impact=3,
                effort=2,
                confidence=1.0,
                affected_urls=list(result.sitemap_errors),
                evidence={
                    "errors": result.sitemap_errors,
                    "statuses": {
                        url: result.sitemap_statuses.get(url) for url in result.sitemap_errors
                    },
                },
                recommendation="檢查受影響檔案的狀態與來源宣告，確認檔案可供讀取後再掃描。",
                validation=["核對每個 sitemap 或子檔的回應及網址清單。"],
                owner=Mode.ENGINEER,
                sources=["sitemaps-protocol"],
            )
        )
    if not documents:
        if not require_urls or result.sitemap_errors or result.sitemap_pending:
            return findings
        findings.append(
            Finding(
                id=next_id("sitemap_missing"),
                title="在已檢查的位置找不到 sitemap",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P2,
                impact=3,
                effort=2,
                confidence=0.8,
                affected_urls=list(result.sitemap_sources) or ["/sitemap.xml"],
                evidence={"checked": result.sitemap_sources},
                recommendation="建立 sitemap.xml 並列出所有應被索引的正規 URL，協助搜尋引擎"
                "更完整地發現與索引網站內容。",
                validation=["確認 /sitemap.xml 回傳 200 且為合法 XML"],
                owner=Mode.ENGINEER,
                sources=["sitemaps-protocol"],
            )
        )
        return findings

    for url, body in documents.items():
        parsed = parse_sitemap(body, result.sitemap_bases.get(url, url))
        if not require_urls and parsed.kind == "urlset" and not parsed.count:
            continue
        message = parsed.problem
        category = parsed.category
        if message:
            findings.append(
                Finding(
                    id=next_id(category),
                    title=f"Sitemap 需要修正：{message}",
                    mode=Mode.CONSULTANT,
                    category="indexability",
                    severity=Severity.P2 if category == "sitemap_too_large" else Severity.P1,
                    impact=4,
                    effort=2,
                    confidence=1.0,
                    affected_urls=[url],
                    evidence={"reason": message, "source": result.sitemap_sources.get(url)},
                    recommendation="依 sitemap 格式修正網址清單，使用完整網址並確認檔案可讀取。",
                    validation=["核對 sitemap 命名空間、根元素、項目與 loc，再重新抓取。"],
                    owner=Mode.ENGINEER,
                    sources=["sitemaps-protocol"],
                )
            )

    return findings


def _check_https(result: CrawlResult, next_id) -> list[Finding]:
    findings: list[Finding] = []
    http_pages = [
        url
        for url, page in result.pages.items()
        if 200 <= page.status_code < 300 and urlparse(page.final_url or url).scheme == "http"
    ]
    if http_pages:
        findings.append(
            Finding(
                id=next_id("https_missing"),
                title="這些網址最終仍以 HTTP 提供內容",
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


def _check_page_metadata(parsed: dict[str, BeautifulSoup], next_id) -> list[Finding]:
    findings: list[Finding] = []
    missing_title: list[str] = []
    missing_meta_description: list[str] = []
    missing_h1: list[str] = []
    multiple_h1: list[str] = []
    title_to_urls: dict[str, list[str]] = {}
    canonical_conflicts: list[str] = []

    for url, soup in parsed.items():
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
        example_groups = {title: urls[:5] for title, urls in list(duplicate_title_groups.items())[:5]}
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
                affected_urls=affected,
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
        affected_urls=affected_urls,
        evidence={"affected_count": len(affected_urls)},
        recommendation=recommendation,
        validation=["重新爬取確認問題已修正"],
        owner=Mode.ENGINEER,
        sources=["google-search-essentials"],
    )


def _check_noindex(noindex: dict[str, list[str]], next_id) -> list[Finding]:
    findings: list[Finding] = []
    noindex_urls = list(noindex)
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
                evidence={
                    "noindex_count": len(noindex_urls),
                    "rules": {url: noindex[url] for url in noindex_urls[:50]},
                },
                recommendation="確認這些頁面是否應該被搜尋引擎索引。如果是重要頁面被誤植 "
                "noindex（常見於模板繼承錯誤或 CMS 設定疏漏），請移除 "
                "noindex 設定；如果本來就不該被索引，則此為預期行為。",
                validation=["重新爬取確認 noindex 設定符合預期"],
                owner=Mode.ENGINEER,
                sources=["google-search-essentials"],
            )
        )

    return findings


def _check_canonical_target(
    parsed: dict[str, BeautifulSoup], result: CrawlResult, noindex: dict, next_id
) -> list[Finding]:
    """檢查 canonical 目標是否有問題：指向不同網域（外站）、或指向本站但該
    目標頁其實回傳非 200。這類錯誤會讓搜尋引擎把權重導到錯的地方，比「多個
    canonical」更隱蔽也更常見。
    """
    findings: list[Finding] = []
    cross_domain: list[str] = []

    snapshots = {}
    for url, snapshot in result.pages.items():
        snapshots[_canonicalize_url_for_comparison(url)] = snapshot
        snapshots.setdefault(_canonicalize_url_for_comparison(snapshot.final_url or url), snapshot)
    bad_targets = {}
    unverified = {}
    for url, soup in parsed.items():
        page_host = urlparse(url).netloc
        for link in soup.find_all("link", rel="canonical", href=True):
            href = link["href"].strip()
            if not href:
                continue
            target = _canonicalize_url_for_comparison(urljoin(document_base(url, soup), href))
            target_host = urlparse(target).netloc
            if (
                page_host
                and target_host
                and _normalize_host(target_host) != _normalize_host(page_host)
            ):
                cross_domain.append(f"{url} → {target}")
                continue
            if not page_host and target_host:
                continue  # A local archive does not identify its public host.
            observed = snapshots.get(target)
            if observed is None or not observed.status_code:
                unverified[url] = target
                continue
            final = _canonicalize_url_for_comparison(observed.final_url or target)
            rules = noindex.get(final, [])
            if observed.status_code >= 400 or (rules and final != url):
                bad_targets[url] = {
                    "target": target,
                    "status": observed.status_code,
                    "rules": rules,
                }

    if bad_targets:
        findings.append(
            Finding(
                id=next_id("canonical_target_unindexable"),
                title="正規網址指向無法收錄的頁面",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P1,
                impact=4,
                effort=2,
                confidence=1.0,
                affected_urls=list(bad_targets)[:50],
                evidence={"examples": dict(list(bad_targets.items())[:50])},
                recommendation="逐一確認來源頁的 canonical，指定可收錄且內容相符的正常網址。",
                validation=["再次抓取來源及目的網址，核對 HTTP 狀態與索引指令。"],
                owner=Mode.ENGINEER,
                sources=["google-search-essentials"],
            )
        )
    result.unverified_canonicals = unverified
    if cross_domain:
        findings.append(
            Finding(
                id=next_id("canonical_cross_domain"),
                title=f"{len(cross_domain)} 個頁面的 canonical 指向不同網域（請確認是否刻意）",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P1,
                impact=4,
                effort=2,
                confidence=0.7,
                affected_urls=[c.split(" → ")[0] for c in cross_domain[:50]],
                evidence={"examples": cross_domain[:10]},
                recommendation="canonical 指向其他網域代表你把這些頁面的搜尋權重讓給了外站。"
                "這有時是刻意的（內容轉載授權 syndication、品牌多網域整併、舊站遷移），"
                "有時是設定錯誤。請逐一確認：若非刻意，把 canonical 改回指向本站自身的"
                "正規網址；若是刻意授權，則為預期行為。",
                validation=["逐一確認 canonical 目標網域是否符合預期"],
                owner=Mode.ENGINEER,
                sources=["google-search-essentials"],
            )
        )
    return findings


def _check_social_metadata(
    parsed: dict[str, BeautifulSoup], noindex: dict, next_id
) -> list[Finding]:
    """檢查 Open Graph / Twitter Card 是否存在。缺這些不影響索引，但會讓頁面
    被分享到社群時沒有預覽圖與標題，大幅降低點擊率——這是很常被忽略、但補起來
    很划算的呈現優化。
    """
    findings: list[Finding] = []
    missing_og: list[str] = []

    for url, soup in parsed.items():
        # 降噪：明顯的 API/後台/系統路徑不需要社群分享卡片，缺 OG 不視為問題。
        path = urlparse(url).path.lower()
        if any(hint in path for hint in _NON_SOCIAL_PATH_HINTS):
            continue
        # noindex 頁本來就不打算被搜尋/分享，缺 OG 不報。
        if url in noindex:
            continue
        has_og_title = soup.find("meta", attrs={"property": "og:title"}) is not None
        has_og_image = soup.find("meta", attrs={"property": "og:image"}) is not None
        if not (has_og_title and has_og_image):
            missing_og.append(url)

    if missing_og:
        findings.append(
            Finding(
                id=next_id("missing_open_graph"),
                title=f"{len(missing_og)} 個頁面缺少完整的 Open Graph（og:title / og:image）",
                mode=Mode.CONSULTANT,
                category="content_quality",
                severity=Severity.P2,
                impact=2,
                effort=1,
                confidence=0.9,
                affected_urls=missing_og[:50],
                evidence={"missing_count": len(missing_og)},
                recommendation="為每個重要頁面補上 og:title、og:description、og:image，"
                "頁面被分享到 Facebook / LINE / Slack 等平台時才會顯示吸引人的預覽卡片，"
                "提高點擊率。範例：<meta property=\"og:title\" content=\"頁面標題\"> 與 "
                "<meta property=\"og:image\" content=\"https://.../cover.jpg\">。",
                validation=["用社群分享除錯工具預覽分享卡片是否正常顯示"],
                owner=Mode.ENGINEER,
                sources=["open-graph-protocol"],
            )
        )
    return findings


def _check_structured_data(parsed: dict[str, BeautifulSoup], next_id) -> list[Finding]:
    """檢查 JSON-LD 結構化資料：是否存在、以及能不能被正確 parse。壞掉的 JSON-LD
    會讓搜尋引擎拿不到 rich result，但頁面上看不出問題，很容易被忽略。
    """
    findings: list[Finding] = []
    invalid_jsonld: list[str] = []

    for url, soup in parsed.items():
        scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
        for script in scripts:
            raw = script.string or script.get_text()
            if not raw or not raw.strip():
                continue
            try:
                json.loads(raw)
            except (ValueError, TypeError):
                invalid_jsonld.append(url)
                break

    if invalid_jsonld:
        findings.append(
            Finding(
                id=next_id("invalid_json_ld"),
                title=f"{len(invalid_jsonld)} 個頁面的 JSON-LD 結構化資料無法解析",
                mode=Mode.CONSULTANT,
                category="content_quality",
                severity=Severity.P2,
                impact=3,
                effort=2,
                confidence=0.9,
                affected_urls=invalid_jsonld[:50],
                evidence={"invalid_count": len(invalid_jsonld)},
                recommendation="這些頁面的 JSON-LD 語法有誤，搜尋引擎無法讀取，會失去 "
                "rich result（星等、麵包屑、FAQ 等）機會。請用官方結構化資料測試工具"
                "驗證並修正 JSON 語法。",
                validation=["用結構化資料測試工具確認可正確解析且無錯誤"],
                owner=Mode.ENGINEER,
                sources=["schema-org"],
            )
        )
    return findings


def _check_orphan_pages(
    result: CrawlResult, seed_url: str, next_id, excluded: set[str]
) -> list[Finding]:
    findings: list[Finding] = []
    orphans = [
        url
        for url in find_orphan_pages(result, seed_url)
        if _canonicalize_url_for_comparison(result.pages[url].final_url or url) not in excluded
        and not result.pages[url].redirect_chain
    ]
    if orphans:
        findings.append(
            Finding(
                id=next_id("orphan_pages"),
                title=f"此次掃描未找到其他頁面連入的網址共 {len(orphans)} 個",
                mode=Mode.CONSULTANT,
                category="internal_linking",
                severity=Severity.P2,
                impact=3,
                effort=2,
                confidence=0.7,
                affected_urls=orphans[:50],
                evidence={"orphan_count": len(orphans), "urls_crawled": len(result.pages)},
                recommendation="為這些頁面建立來自相關頁面的內部連結，孤兒頁難以被搜尋引擎"
                "透過爬取發現，也無法從內部連結獲得權重傳遞。",
                validation=["重新爬取確認這些頁面已被其他頁面連結"],
                owner=Mode.CONSULTANT,
            )
        )
    return findings


def _sitemap_has_hreflang(sitemap_xml: str | None) -> bool:
    """粗略檢查 sitemap.xml 是否使用 xhtml:link 宣告 hreflang（sitemap 版本
    的多語言宣告形式）。只做字串層級檢查，不完整解析 sitemap 結構——這裡
    只需要判斷「是否同時存在」，不需要比對內容是否正確。
    """
    if not sitemap_xml:
        return False
    return 'rel="alternate"' in sitemap_xml and "hreflang" in sitemap_xml


def extract_hreflang_matrix(result: CrawlResult) -> dict[str, dict[str, str]]:
    """回傳「頁面 x 語言」的完整 hreflang 宣告矩陣：{頁面 URL: {語言代碼:
    宣告的 href}}，只包含有 hreflang 宣告的頁面。

    給 scan_runner 組 `Report.scan_stats["hreflang_matrix"]` 用（供
    HTML 報告畫矩陣表格），跟 `_check_hreflang()` 共用同一份底層 parsing
    邏輯（`_extract_page_hreflang_declarations()`），避免兩處各自重新解析
    一次 HTML 造成邏輯漂移。這是獨立的公開函式而非修改 `analyze_technical_
    seo()` 的回傳型別，因為那是本模組對外的穩定介面，改動型別會牽動所有
    呼叫端（包含既有測試）。
    """
    parsed = _parsed_pages(result)
    return _extract_page_hreflang_declarations(parsed)


def _extract_page_hreflang_declarations(parsed: dict[str, BeautifulSoup]) -> dict[str, dict[str, str]]:
    """逐頁解析 `<link rel="alternate" hreflang="...">` 標籤，回傳
    {頁面 URL: {語言代碼: 宣告的 href（未正規化的原始值，用於顯示）}}，
    只包含至少有一個 hreflang 宣告的頁面。
    """
    page_declarations: dict[str, dict[str, str]] = {}
    for url, soup in parsed.items():
        alternate_tags = soup.find_all("link", rel="alternate", hreflang=True)
        if not alternate_tags:
            continue

        declarations: dict[str, str] = {}
        for tag in alternate_tags:
            code = (tag.get("hreflang") or "").strip()
            href = tag.get("href") or ""
            if not code or not href:
                continue
            declarations[code] = href
        page_declarations[url] = declarations
    return page_declarations


def _check_hreflang(
    parsed: dict[str, BeautifulSoup], result: CrawlResult, seed_url: str, next_id
) -> list[Finding]:
    """檢查 hreflang 標籤（<link rel="alternate" hreflang="...">）的常見問題：
    缺 self-reference、重複語言代碼、格式不合法、非互相對稱、指向授權範圍外
    的網址、以及 HTML/sitemap 兩種宣告形式混用的跡象。

    只檢查 HTML <link> 這種宣告形式；HTTP header 形式的 hreflang 這輪不做。
    non_reciprocal 檢查需要先收集全站的宣告對照表，因此必須在拿到完整的
    parsed（所有頁面都解析過）之後才能執行，屬於全站層級檢查。
    """
    findings: list[Finding] = []
    site_origin = seed_url if seed_url.startswith(("http://", "https://")) else None

    page_declarations = _extract_page_hreflang_declarations(parsed)
    aliases = {
        _canonicalize_url_for_comparison(requested): _canonicalize_url_for_comparison(
            snapshot.final_url
        )
        for url, snapshot in result.pages.items()
        if snapshot.status_code == 200 and snapshot.final_url
        for requested in (*snapshot.redirect_chain, url)
    }

    def resolved(key):
        return aliases.get(key, key)

    missing_self_ref: list[str] = []
    duplicate_language: list[str] = []
    invalid_code_pages: dict[str, list[str]] = {}
    out_of_scope_pages: dict[str, list[str]] = {}

    for url, soup in parsed.items():
        declarations = page_declarations.get(url)
        if declarations is None:
            continue

        # 重複語言代碼的偵測需要逐一遍歷原始 tag（而非去重後的 declarations
        # dict），因為同一語言代碼出現兩次時 dict 只會保留最後一個值，count
        # 資訊會遺失。
        codes_seen: Counter[str] = Counter()
        for tag in soup.find_all("link", rel="alternate", hreflang=True):
            code = (tag.get("hreflang") or "").strip()
            if code and (tag.get("href") or ""):
                codes_seen[code.casefold()] += 1

        invalid_codes: list[str] = []
        out_of_scope: list[str] = []

        for code, href in declarations.items():
            if not valid_hreflang(code):
                invalid_codes.append(code)

            target_absolute = urljoin(document_base(url, soup), href)
            if site_origin:
                target_netloc = urlparse(target_absolute).netloc
                seed_netloc = urlparse(site_origin).netloc
                if (
                    target_netloc
                    and _normalize_host(target_netloc) != _normalize_host(seed_netloc)
                ):
                    out_of_scope.append(href)

        has_self_reference = any(
            resolved(_canonicalize_url_for_comparison(urljoin(document_base(url, soup), href)))
            == url
            for href in declarations.values()
        )
        if not has_self_reference:
            missing_self_ref.append(url)

        if any(count > 1 for count in codes_seen.values()):
            duplicate_language.append(url)

        if invalid_codes:
            invalid_code_pages[url] = invalid_codes
        if out_of_scope:
            out_of_scope_pages[url] = out_of_scope

    if not page_declarations:
        return findings

    # non-reciprocal：只在目標頁確實在本次 crawl 範圍內時才判斷（用「所有
    # 被爬到的頁面」parsed，不是「有 hreflang 宣告的頁面」page_declarations
    # ——目標頁存在但完全沒有 hreflang 宣告，本身就是一種 non-reciprocal，
    # 不該因為它不在 page_declarations 裡就被略過），避免把「目標頁根本
    # 沒被爬到」誤判成「目標頁沒有指回來」。
    canonical_to_crawled_page = {
        _canonicalize_url_for_comparison(url): url for url in parsed
    }
    redirected = {}
    non_reciprocal_pairs: list[str] = []
    for source_url, declarations in page_declarations.items():
        for code, href in declarations.items():
            target_absolute = urljoin(document_base(source_url, parsed[source_url]), href)
            target_key = _canonicalize_url_for_comparison(target_absolute)
            final_key = resolved(target_key)
            if final_key != target_key:
                redirected.setdefault(source_url, []).append(
                    {"declared": target_absolute, "final": final_key}
                )
            if code.casefold() == "x-default":
                continue
            target_original = canonical_to_crawled_page.get(final_key)
            if target_original is None or target_original == source_url:
                # 目標頁不在本次 crawl 範圍內：無法驗證是否指回，不誤報。
                continue
            target_declarations = page_declarations.get(target_original, {})
            source_key = _canonicalize_url_for_comparison(source_url)
            points_back = any(
                resolved(
                    _canonicalize_url_for_comparison(
                        urljoin(document_base(target_original, parsed[target_original]), back_href)
                    )
                )
                == source_key
                for back_href in target_declarations.values()
            )
            if not points_back:
                non_reciprocal_pairs.append(f"{source_url} -> {href}")

    if redirected:
        findings.append(
            Finding(
                id=next_id("hreflang_redirect"),
                title="hreflang 仍指向轉址前的網址",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P3,
                impact=2,
                effort=1,
                confidence=1.0,
                affected_urls=list(redirected),
                evidence={"targets": redirected},
                recommendation="將語系標記更新為實際回應的最終網址。",
                validation=["核對轉址來源、最終頁及相互參照。"],
                owner=Mode.ENGINEER,
                sources=["hreflang"],
            )
        )

    if missing_self_ref:
        findings.append(
            Finding(
                id=next_id("hreflang_missing_self_reference"),
                title=f"{len(missing_self_ref)} 個頁面的 hreflang 宣告缺少 self-reference",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P2,
                impact=2,
                effort=1,
                confidence=0.8,
                affected_urls=missing_self_ref[:50],
                evidence={"count": len(missing_self_ref)},
                recommendation="每個有 hreflang 宣告的頁面，都應該包含一條指向自己的 "
                "hreflang（self-reference），否則搜尋引擎可能無法正確理解這組頁面的"
                "語言/地區對應關係。",
                validation=["確認每個頁面的 hreflang alternate 清單包含自己"],
                owner=Mode.ENGINEER,
                sources=["hreflang"],
            )
        )

    if duplicate_language:
        findings.append(
            Finding(
                id=next_id("hreflang_duplicate_language"),
                title=f"{len(duplicate_language)} 個頁面對同一語言代碼宣告了多個 hreflang",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P2,
                impact=2,
                effort=1,
                confidence=0.85,
                affected_urls=duplicate_language[:50],
                evidence={"count": len(duplicate_language)},
                recommendation="同一個語言/地區代碼在同一頁只能宣告一次 hreflang，"
                "重複宣告會讓搜尋引擎難以判斷該以哪一個為準。",
                validation=["確認每個 hreflang 代碼在單一頁面只出現一次"],
                owner=Mode.ENGINEER,
                sources=["hreflang"],
            )
        )

    if invalid_code_pages:
        findings.append(
            Finding(
                id=next_id("hreflang_invalid_code"),
                title=f"{len(invalid_code_pages)} 個頁面的 hreflang 代碼格式不正確",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P3,
                impact=2,
                effort=1,
                confidence=0.7,
                affected_urls=list(invalid_code_pages.keys())[:50],
                evidence={"examples": dict(list(invalid_code_pages.items())[:10])},
                recommendation="使用語言代碼，可再指定文字系統、地區，例如 zh-Hant-TW，或選 x-default。此項檢查語法格式。",
                validation=["確認 hreflang 屬性值符合語言/地區代碼格式"],
                owner=Mode.ENGINEER,
                sources=["hreflang"],
            )
        )

    if out_of_scope_pages:
        findings.append(
            Finding(
                id=next_id("hreflang_out_of_scope"),
                title=f"{len(out_of_scope_pages)} 個頁面的 hreflang 指向網站授權範圍外的網域",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P3,
                impact=1,
                effort=1,
                confidence=0.6,
                affected_urls=list(out_of_scope_pages.keys())[:50],
                evidence={"examples": dict(list(out_of_scope_pages.items())[:10])},
                recommendation="部分 hreflang 目標指向了不同網域。如果這是刻意為之的"
                "國際站群（例如 example.com 對應 example.de），可以忽略此提示；"
                "如果不是，請確認網址是否填寫錯誤。",
                validation=["確認跨網域的 hreflang 目標是否為刻意的國際站群設計"],
                owner=Mode.CONSULTANT,
            )
        )

    if non_reciprocal_pairs:
        findings.append(
            Finding(
                id=next_id("hreflang_non_reciprocal"),
                title=f"發現 {len(non_reciprocal_pairs)} 組 hreflang 沒有互相指回",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P2,
                impact=2,
                effort=2,
                confidence=0.75,
                affected_urls=[pair.split(" -> ")[0] for pair in non_reciprocal_pairs][:50],
                evidence={"examples": non_reciprocal_pairs[:10]},
                recommendation="hreflang 宣告應該互相對稱：A 頁面宣告指向 B，B 頁面也應該"
                "宣告指回 A。單向宣告可能讓搜尋引擎忽略整組 hreflang 關係。"
                "（只檢查了本次 crawl 範圍內確實抓到的頁面，若目標頁未被爬到則不列入判斷。）",
                validation=["確認每一組互相參照的頁面都有對稱的 hreflang 宣告"],
                owner=Mode.ENGINEER,
                sources=["hreflang"],
            )
        )

    if any(
        _sitemap_has_hreflang(body)
        for body in (result.sitemap_documents.values() or [result.sitemap_xml])
    ):
        findings.append(
            Finding(
                id=next_id("hreflang_mixed_implementation"),
                title="同時偵測到 HTML 與 sitemap 兩種 hreflang 宣告形式",
                mode=Mode.CONSULTANT,
                category="indexability",
                severity=Severity.P3,
                impact=1,
                effort=2,
                confidence=0.5,
                affected_urls=list(page_declarations.keys())[:10],
                evidence={"sitemap_has_hreflang": True, "pages_with_html_hreflang": len(page_declarations)},
                recommendation="hreflang 可以用 HTML <link> 標籤、HTTP header、或 sitemap "
                "的 xhtml:link 三種形式宣告，建議三選一貫徹使用，混用容易造成兩處宣告"
                "不一致時難以排查問題（這裡只偵測到「同時存在」的跡象，不判斷哪一份是"
                "正確的）。",
                validation=["確認團隊只維護單一種 hreflang 宣告來源"],
                owner=Mode.CONSULTANT,
            )
        )

    return findings


def _check_cwv_static_hints(parsed: dict[str, BeautifulSoup], next_id) -> list[Finding]:
    """純靜態 HTML 分析找出可能影響 Core Web Vitals 的線索，不是真實的
    Lighthouse/CWV 分數量測（那需要真實瀏覽器渲染）。只檢查：
    - <img> 缺少 width/height 屬性（可能造成 layout shift）
    - 單頁 blocking <script>（沒有 defer/async）數量過多
    """
    findings: list[Finding] = []
    missing_dimensions: list[str] = []
    many_blocking_scripts: list[str] = []

    for url, soup in parsed.items():
        images = soup.find_all("img")
        if any(not img.get("width") or not img.get("height") for img in images):
            missing_dimensions.append(url)

        blocking_scripts = [
            script
            for script in soup.find_all("script", src=True)
            if script.get("defer") is None
            and script.get("async") is None
            and (script.get("type") or "").strip().lower()
            in {
                "",
                "text/javascript",
                "application/javascript",
                "text/ecmascript",
                "application/ecmascript",
                "application/x-ecmascript",
                "application/x-javascript",
                "text/x-ecmascript",
                "text/x-javascript",
                "text/jscript",
                "text/livescript",
                "text/javascript1.0",
                "text/javascript1.1",
                "text/javascript1.2",
                "text/javascript1.3",
                "text/javascript1.4",
                "text/javascript1.5",
            }
        ]
        if len(blocking_scripts) >= 3:
            many_blocking_scripts.append(url)

    if missing_dimensions:
        findings.append(
            Finding(
                id=next_id("image_missing_dimensions_hint"),
                title=f"{len(missing_dimensions)} 個頁面有 <img> 缺少 width/height 屬性",
                mode=Mode.CONSULTANT,
                category="performance",
                severity=Severity.P3,
                impact=2,
                effort=1,
                confidence=0.5,
                affected_urls=missing_dimensions[:50],
                evidence={
                    "count": len(missing_dimensions),
                    "note": "只檢查 HTML 屬性是否存在，不驗證數值是否正確，也未考慮 "
                    "CSS aspect-ratio 或容器保留空間等替代做法，可能有誤判。",
                },
                recommendation="為 <img> 補上 width 與 height 屬性（或用 CSS "
                "aspect-ratio 搭配容器保留版面空間），避免圖片載入時造成畫面跳動"
                "（layout shift）。這只是靜態線索，不是實際的 Core Web Vitals 分數。",
                validation=["用瀏覽器開發者工具或 PageSpeed Insights 確認 CLS 分數"],
                owner=Mode.ENGINEER,
                sources=["web-vitals-cls"],
            )
        )

    if many_blocking_scripts:
        findings.append(
            Finding(
                id=next_id("blocking_scripts_hint"),
                title=f"{len(many_blocking_scripts)} 個頁面有多個未使用 defer/async 的 <script>",
                mode=Mode.CONSULTANT,
                category="performance",
                severity=Severity.P3,
                impact=2,
                effort=2,
                confidence=0.5,
                affected_urls=many_blocking_scripts[:50],
                evidence={
                    "count": len(many_blocking_scripts),
                    "note": "只是靜態線索（script 數量與屬性），不是實際的載入時間量測。",
                },
                recommendation="為外部 <script> 標籤加上 defer 或 async 屬性，避免多個"
                "同步載入的 script 阻塞頁面渲染。是否適合加 defer/async 需視該 script "
                "的執行順序需求而定，這裡不會自動修改（可能影響 JS 執行順序）。",
                validation=["用瀏覽器開發者工具的效能面板確認渲染阻塞情況是否改善"],
                owner=Mode.ENGINEER,
                sources=["web-vitals"],
            )
        )

    return findings
