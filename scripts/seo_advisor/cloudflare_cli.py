"""Cloudflare 稽核的 CLI subapp（seo-advisor cloudflare ...）。

安全設計：MVP 只做唯讀盤點（`seo-advisor cloudflare audit`），輸出
Markdown + JSON 報告。redirect rule 的真寫入能力（`CloudflareConnector.
deploy_patch()`）這輪刻意不接 CLI——寫入涉及樂觀鎖 hash 比對與確認流程，
需要比唯讀稽核更完整的人機互動設計（類似 Engineer Mode 的 dry-run +
--confirm 流程），留待後續版本再串接，避免 CLI 提供一個「看起來能用但
安全把關不完整」的寫入入口。
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from seo_advisor.connectors.cloudflare import CloudflareConnector, CloudflareConnectorError
from seo_advisor.env_hints import set_env_var_hint
from seo_advisor.errors import translate_exception
from seo_advisor.security.cloudflare_safety import InvalidZoneIdError

cloudflare_app = typer.Typer(help="Cloudflare 稽核：唯讀盤點 DNS/redirect/cache 設定")
console = Console()

_TOKEN_ENV_VAR = "CLOUDFLARE_API_TOKEN"


@cloudflare_app.command("audit")
def audit(
    zone_id: str = typer.Option(..., "--zone-id", help="Cloudflare Zone ID（32 字元十六進位，見 Dashboard Overview 頁）"),
    zone_name: str = typer.Option(
        None, "--zone-name", help="預期的網域名稱，提供時會驗證與 zone_id 對應的實際網域一致"
    ),
    out: str = typer.Option("./cloudflare-report", "--out", help="報告輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """唯讀盤點指定 zone 的 DNS records、redirect/cache rules、legacy page rules。"""
    import os

    if not os.environ.get(_TOKEN_ENV_VAR):
        console.print(
            f"[red]找不到環境變數 {_TOKEN_ENV_VAR}。[/red]\n"
            f"{set_env_var_hint(_TOKEN_ENV_VAR, 'your-api-token')}"
        )
        raise typer.Exit(code=1)

    try:
        connector = CloudflareConnector(zone_id, zone_name=zone_name)
    except (InvalidZoneIdError, CloudflareConnectorError) as exc:
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    try:
        snapshot = connector.build_snapshot()
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)
    finally:
        connector.close()

    out_path = Path(out)
    out_path.mkdir(parents=True, exist_ok=True)
    json_path = out_path / "cloudflare-report.json"
    md_path = out_path / "cloudflare-report.md"

    json_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(snapshot), encoding="utf-8")

    console.print(f"[bold green]完成！已盤點 zone {snapshot['zone_name']}。[/bold green]")
    console.print(f"  - DNS records：{len(snapshot['dns_records'])} 筆")
    console.print(f"  - Redirect rules：{len(snapshot['redirect_rules'])} 筆")
    console.print(f"  - Cache rules：{len(snapshot['cache_rules'])} 筆")
    console.print(f"  - Legacy page rules：{len(snapshot['page_rules'])} 筆")
    for note in snapshot["permission_notes"]:
        console.print(f"[yellow]提醒：{note}[/yellow]")
    console.print(f"報告：{md_path}")
    console.print(f"機器可讀資料：{json_path}")


def _render_markdown(snapshot: dict) -> str:
    lines = [
        f"# Cloudflare 稽核報告：{snapshot['zone_name']}",
        "",
        f"- Zone ID：{snapshot['zone_id']}",
        "",
        f"## DNS Records（{len(snapshot['dns_records'])} 筆）",
        "",
    ]
    for record in snapshot["dns_records"][:100]:
        lines.append(f"- `{record.get('type', '?')}` {record.get('name', '?')} -> {record.get('content', '?')}")

    lines.append("")
    lines.append(f"## Redirect Rules（{len(snapshot['redirect_rules'])} 筆）")
    lines.append("")
    for rule in snapshot["redirect_rules"][:100]:
        lines.append(f"- {rule.get('description', rule.get('ref', '（未命名規則）'))}")

    lines.append("")
    lines.append(f"## Cache Rules（{len(snapshot['cache_rules'])} 筆）")
    lines.append("")
    for rule in snapshot["cache_rules"][:100]:
        lines.append(f"- {rule.get('description', rule.get('ref', '（未命名規則）'))}")

    lines.append("")
    lines.append(f"## Legacy Page Rules（{len(snapshot['page_rules'])} 筆）")
    lines.append("")
    for rule in snapshot["page_rules"][:100]:
        lines.append(f"- {rule.get('id', '?')}：{rule.get('status', '?')}")

    if snapshot["permission_notes"]:
        lines.append("")
        lines.append("## 提醒")
        lines.append("")
        for note in snapshot["permission_notes"]:
            lines.append(f"- {note}")

    return "\n".join(lines) + "\n"
