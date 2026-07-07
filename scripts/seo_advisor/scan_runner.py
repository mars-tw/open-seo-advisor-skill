"""共用的掃描執行邏輯：CLI 的 audit/start/demo 指令都透過這裡執行實際掃描。

抽出這一層的目的：互動精靈（wizard）、明確指令（audit consultant）、
demo 模式三種入口，應該共用同一套「爬取 -> 分析 -> 產報告」邏輯與同一份
進度提示文字，避免三份程式碼各自維護、行為逐漸不一致。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from seo_advisor.analyzers.technical import analyze_technical_seo
from seo_advisor.beginner_report import render_beginner_markdown
from seo_advisor.connectors.base import WebsiteConnector
from seo_advisor.connectors.http import HTTPConnector
from seo_advisor.connectors.local_archive import LocalArchiveConnector
from seo_advisor.crawler import crawl_site
from seo_advisor.models import Mode, Report, ReportTarget
from seo_advisor.report import build_report, render_json, render_markdown
from seo_advisor.url_utils import normalize_url

ProgressCallback = Callable[[str], None]

_COVERAGE_NOTES = [
    "Core Web Vitals、JavaScript 渲染差異比對、結構化資料驗證、"
    "Search Console/GA4 資料整合尚未實作（見 docs/roadmap.md v0.2.0）。",
]

_UNREACHABLE_ERROR_TYPES = {"timeout", "connect_error"}


class SiteUnreachableError(ConnectionError):
    """網站首頁完全連不上（DNS/連線/逾時失敗）時拋出，避免產出空洞的報告。"""


@dataclass
class ScanOutcome:
    report: Report
    beginner_path: Path
    technical_path: Path
    json_path: Path


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _noop(_: str) -> None:
    return None


def run_consultant_scan(
    *,
    url: str | None,
    source: str | None,
    out_dir: str,
    max_urls: int = 200,
    max_depth: int = 6,
    timeout_seconds: float = 15.0,
    on_progress: ProgressCallback = _noop,
) -> ScanOutcome:
    """執行 Consultant Mode 掃描並寫出三份報告（beginner/技術版/JSON）。

    url 與 source 恰好需提供一個；url 會先經過 normalize_url() 正規化，
    因此呼叫端不需要自己處理「使用者忘記打 https://」的情況。
    """
    if bool(url) == bool(source):
        raise ValueError("必須提供 url 或 source 其中之一，且不可同時提供。")

    generated_at = _now_iso()
    connector: WebsiteConnector
    coverage_notes = list(_COVERAGE_NOTES)

    if url:
        normalized_url = normalize_url(url)
        on_progress(f"準備掃描網站：{normalized_url}")
        connector = HTTPConnector(normalized_url, timeout_seconds=timeout_seconds)
        target = ReportTarget(source_type="http", identifier=normalized_url)
        seed = normalized_url
    else:
        on_progress(f"準備掃描本地來源：{source}")
        connector = LocalArchiveConnector(source)
        target = ReportTarget(
            source_type="local_archive", identifier=str(Path(source).resolve())
        )
        seed = "/"

    try:
        on_progress("第 1/4 步：確認網站連線與基本設定（robots.txt / sitemap.xml）")
        profile = connector.probe()
        coverage_notes.extend(profile.notes)

        if url:
            _preflight_check_reachable(connector, seed, fetched_at=generated_at)

        on_progress("第 2/4 步：逐頁爬取內容")
        crawl_result = crawl_site(
            connector,
            seed_url=seed,
            max_urls=max_urls,
            max_depth=max_depth,
            fetched_at=generated_at,
        )
        on_progress(f"已掃描 {len(crawl_result.pages)} 個頁面")

        on_progress("第 3/4 步：檢查常見 SEO 問題")
        findings = analyze_technical_seo(crawl_result, seed_url=seed)
        on_progress(f"發現 {len(findings)} 項需要留意的問題")

        report = build_report(
            report_id=_derive_report_id(target),
            generated_at=generated_at,
            target=target,
            mode=Mode.CONSULTANT,
            findings=findings,
            coverage_notes=coverage_notes,
            scan_stats={
                "urls_crawled": len(crawl_result.pages),
                "urls_skipped": len(crawl_result.skipped_urls),
                "detected_stack": profile.detected_stack,
            },
        )
    finally:
        connector.close()

    on_progress("第 4/4 步：整理報告")
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    beginner_path = out_path / "report-beginner.md"
    technical_path = out_path / "report.md"
    json_path = out_path / "report.json"

    beginner_path.write_text(render_beginner_markdown(report), encoding="utf-8")
    technical_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(render_json(report), encoding="utf-8")

    return ScanOutcome(
        report=report,
        beginner_path=beginner_path,
        technical_path=technical_path,
        json_path=json_path,
    )


def _preflight_check_reachable(connector: WebsiteConnector, seed_url: str, *, fetched_at: str) -> None:
    """在正式爬取前先確認首頁連得上，避免對完全連不上的網站產出一份看起來
    「掃描完成」但其實什麼內容都沒抓到的空洞報告，誤導新手以為網站沒問題。

    只擋「連線層級」的失敗（DNS/連線/逾時），HTTP 4xx/5xx 狀態碼視為
    「網站有回應但頁面有問題」，仍應正常產出報告讓使用者看到這個發現。
    """
    snapshot = connector.fetch_url(seed_url, fetched_at=fetched_at)
    if snapshot.status_code == 0 and snapshot.fetch_error_type in _UNREACHABLE_ERROR_TYPES:
        raise SiteUnreachableError(
            f"無法連線到 {seed_url}（{snapshot.fetch_error_message or snapshot.fetch_error_type}）"
        )


def _derive_report_id(target: ReportTarget) -> str:
    slug = (
        target.identifier.replace("https://", "")
        .replace("http://", "")
        .strip("/")
        .replace("/", "-")
        .replace(":", "-")
        .replace("\\", "-")
    )
    slug = slug[:40] if slug else "site"
    return f"seo-report-{slug}"
