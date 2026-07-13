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
from seo_advisor.connectors.cpanel import CPanelConnector
from seo_advisor.connectors.http import HTTPConnector
from seo_advisor.connectors.local_archive import LocalArchiveConnector
from seo_advisor.connectors.ssh import SSHConnector
from seo_advisor.crawler import crawl_site
from seo_advisor.models import Mode, Report, ReportTarget, SafetyPolicy
from seo_advisor.report import build_report, render_json, render_markdown
from seo_advisor.url_utils import normalize_url


@dataclass
class SSHSourceOptions:
    """`audit consultant --source ssh` 需要的連線參數，從 CLI 收集後傳給
    `run_consultant_scan`，讓 scan_runner 不需要知道 CLI 參數解析的細節。
    """

    host: str
    user: str
    remote_root: str
    confirm_connect: str
    port: int = 22
    key_path: str | None = None
    known_hosts_path: str | None = None
    allow_private_network: bool = False

    @staticmethod
    def missing_required_fields(
        *, host: str | None, user: str | None, remote_root: str | None, confirm_connect: str | None
    ) -> list[str]:
        """給 CLI 用的必要欄位檢查：回傳缺少的 CLI 旗標名稱清單（可能不只
        一個），讓使用者一次看到所有需要補齊的參數，而不是逐一嘗試才發現
        下一個缺少的參數。與 dataclass 本身的必填欄位（沒有預設值）驗證
        目的相同，但這裡產出的是給終端機使用者看的旗標名稱，不是
        Python 建構子的 TypeError。
        """
        missing = []
        if not host:
            missing.append("--ssh-host")
        if not user:
            missing.append("--ssh-user")
        if not remote_root:
            missing.append("--ssh-remote-root")
        if not confirm_connect:
            missing.append("--ssh-confirm")
        return missing


@dataclass
class CPanelSourceOptions:
    """`audit consultant --source cpanel` 需要的連線參數。"""

    host: str
    username: str
    remote_root: str
    confirm_connect: str
    port: int = 2083
    allow_private_network: bool = False

    @staticmethod
    def missing_required_fields(
        *, host: str | None, username: str | None, remote_root: str | None, confirm_connect: str | None
    ) -> list[str]:
        missing = []
        if not host:
            missing.append("--cpanel-host")
        if not username:
            missing.append("--cpanel-user")
        if not remote_root:
            missing.append("--cpanel-remote-root")
        if not confirm_connect:
            missing.append("--cpanel-confirm")
        return missing


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
    ssh_options: SSHSourceOptions | None = None,
    cpanel_options: CPanelSourceOptions | None = None,
) -> ScanOutcome:
    """執行 Consultant Mode 掃描並寫出三份報告（beginner/技術版/JSON）。

    url、source（本地路徑）、source="ssh"+ssh_options、source="cpanel"+
    cpanel_options 四者恰好需提供一個；url 會先經過 normalize_url() 正規化，
    因此呼叫端不需要自己處理「使用者忘記打 https://」的情況。
    """
    is_ssh = source == "ssh"
    is_cpanel = source == "cpanel"
    if ssh_options is not None and not is_ssh:
        raise ValueError("提供 ssh_options 時 source 必須是 'ssh'。")
    if is_ssh and ssh_options is None:
        raise ValueError("source='ssh' 時必須提供 ssh_options。")
    if cpanel_options is not None and not is_cpanel:
        raise ValueError("提供 cpanel_options 時 source 必須是 'cpanel'。")
    if is_cpanel and cpanel_options is None:
        raise ValueError("source='cpanel' 時必須提供 cpanel_options。")

    provided_count = sum([bool(url), bool(source) and not is_ssh and not is_cpanel, is_ssh, is_cpanel])
    if provided_count != 1:
        raise ValueError(
            "必須提供 url、source（本地路徑）、source='ssh' 或 source='cpanel' 四者恰好其中之一。"
        )

    generated_at = _now_iso()
    connector: WebsiteConnector
    coverage_notes = list(_COVERAGE_NOTES)

    if url:
        normalized_url = normalize_url(url)
        on_progress(f"準備掃描網站：{normalized_url}")
        connector = HTTPConnector(normalized_url, timeout_seconds=timeout_seconds)
        target = ReportTarget(source_type="http", identifier=normalized_url)
        seed = normalized_url
    elif is_ssh:
        assert ssh_options is not None  # 上面已驗證，這裡讓型別檢查器安心
        on_progress(f"準備掃描遠端伺服器：{ssh_options.user}@{ssh_options.host}:{ssh_options.remote_root}")
        connector = SSHConnector(
            ssh_options.host,
            user=ssh_options.user,
            remote_root=ssh_options.remote_root,
            port=ssh_options.port,
            key_path=ssh_options.key_path,
            known_hosts_path=ssh_options.known_hosts_path,
            confirm_connect=ssh_options.confirm_connect,
            allow_private_network=ssh_options.allow_private_network,
            timeout_seconds=timeout_seconds,
            policy=SafetyPolicy(
                allowed_capabilities={"read_files", "read_urls"},
                allow_private_network=ssh_options.allow_private_network,
            ),
        )
        target = ReportTarget(
            source_type="ssh",
            identifier=f"ssh:{ssh_options.user}@{ssh_options.host}:{ssh_options.remote_root}",
        )
        seed = "/"
    elif is_cpanel:
        assert cpanel_options is not None  # 上面已驗證，這裡讓型別檢查器安心
        on_progress(
            f"準備掃描 cPanel 網站：{cpanel_options.username}@{cpanel_options.host}:"
            f"{cpanel_options.remote_root}"
        )
        connector = CPanelConnector(
            cpanel_options.host,
            username=cpanel_options.username,
            remote_root=cpanel_options.remote_root,
            port=cpanel_options.port,
            confirm_connect=cpanel_options.confirm_connect,
            allow_private_network=cpanel_options.allow_private_network,
            timeout_seconds=timeout_seconds,
            policy=SafetyPolicy(
                allowed_capabilities={"read_files", "read_urls"},
                allow_private_network=cpanel_options.allow_private_network,
            ),
        )
        target = ReportTarget(
            source_type="cpanel",
            identifier=f"cpanel:{cpanel_options.username}@{cpanel_options.host}:{cpanel_options.remote_root}",
        )
        seed = "/"
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
