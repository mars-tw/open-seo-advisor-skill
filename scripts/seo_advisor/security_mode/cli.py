"""Security Mode 的 CLI subapp（seo-advisor security ...）。

安全設計：純被動式檢查，不做任何攻擊性測試。暴露檔案/目錄列表探測、
cloaking UA 比較、惡意重導 Referer 比較都需要明確授權確認
（--confirm-authorized "AUDIT <host>"）才會執行；--passive-only 可跳過
確認，但只做完全被動的檢查（HTTPS/HSTS/mixed content/SEO spam/CMS 版本
提示），不涵蓋任何需要額外發送探測性請求的項目。
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from seo_advisor.errors import translate_exception
from seo_advisor.security_mode.report import render_security_report_json, render_security_report_markdown
from seo_advisor.security_mode.runner import AuthorizationRequiredError, build_confirmation_phrase, run_security_audit
from seo_advisor.url_utils import normalize_url

security_app = typer.Typer(help="Security Mode：被動式資安風險掃描（不做任何攻擊性測試）")
console = Console()


@security_app.command("audit")
def audit(
    url: str = typer.Option(..., "--url", help="要檢查的網址（只能檢查你有權管理的網站）"),
    confirm_authorized: str = typer.Option(
        None, "--confirm-authorized",
        help='確認你有權對此網站執行安全檢查，需輸入 "AUDIT <網域>"（暴露檔案/目錄列表探測需要此確認）',
    ),
    passive_only: bool = typer.Option(
        False, "--passive-only",
        help="只做完全被動的檢查（HTTPS/SEO spam/CMS 版本提示），不探測任何路徑、"
        "不做 cloaking/惡意重導比較，不需授權確認",
    ),
    no_bot_compare: bool = typer.Option(False, "--no-bot-compare", help="跳過 Googlebot UA 內容差異比較"),
    out: str = typer.Option("./security-report", "--out", help="輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """對指定網址執行被動式資安健檢，產出 Markdown + JSON 報告。"""
    try:
        normalized_url = normalize_url(url)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    if not passive_only and not confirm_authorized:
        console.print(
            "[yellow]Security Mode 的暴露檔案/目錄列表檢查會對這個網站發送額外的安全檢查請求。"
            "只能用於你自己管理、或已取得明確授權的網站。[/yellow]\n"
            f'請加上 --confirm-authorized "{build_confirmation_phrase(normalized_url)}" 確認你有這個授權，\n'
            "或加上 --passive-only 只做完全被動的檢查（不需授權確認，但涵蓋範圍較小）。"
        )
        raise typer.Exit(code=1)

    try:
        report = run_security_audit(
            normalized_url,
            passive_only=passive_only,
            confirm_authorized=confirm_authorized,
            skip_bot_compare=no_bot_compare,
        )
    except AuthorizationRequiredError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    out_path = Path(out)
    out_path.mkdir(parents=True, exist_ok=True)
    md_path = out_path / "security-report.md"
    json_path = out_path / "security-report.json"
    md_path.write_text(render_security_report_markdown(report), encoding="utf-8")
    json_path.write_text(render_security_report_json(report), encoding="utf-8")

    severity_counts = {}
    for finding in report.findings:
        severity_counts[finding.severity.value] = severity_counts.get(finding.severity.value, 0) + 1

    console.print(
        f"[bold green]完成！共 {len(report.findings)} 項發現。[/bold green]"
        + (f"（{severity_counts}）" if severity_counts else "")
    )
    console.print(f"報告：{md_path}")
    console.print(f"機器可讀資料：{json_path}")
    if report.passive_only:
        console.print(
            "[dim]這是被動模式，未檢查暴露檔案/目錄列表。"
            '加上 --confirm-authorized "AUDIT <網域>" 可執行完整檢查。[/dim]'
        )
