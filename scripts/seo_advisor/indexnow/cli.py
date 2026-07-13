"""IndexNow 的 CLI subapp（seo-advisor indexnow ...）。

安全設計：預設一律 dry-run（只做 key 格式驗證 + URL scope 驗證並輸出預覽
報告，不對外發送任何請求）。真的送出通知需要同時滿足 `--send` 與
`--confirm "SUBMIT INDEXNOW <host> <url_count>"`，確認字串綁定「這次
到底要送幾個 URL 給哪個 host」，避免使用者不小心把測試用的 dry-run
指令複製貼上一個 `--send` 就送出，或是送出的數量和預覽時看到的不一致。

IndexNow 不接掛在 Engineer Mode fixer 套用流程之後自動觸發：Engineer Mode
的 dry-run/測試環境很容易被誤用來連帶觸發真實的搜尋引擎通知，這輪刻意
維持為獨立指令，由使用者自行決定發布時機。
"""

from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.console import Console

from seo_advisor.errors import translate_exception
from seo_advisor.fixers.safety import verify_confirmation
from seo_advisor.indexnow.client import resolve_endpoint
from seo_advisor.indexnow.key import InvalidIndexNowKeyError, generate_key, validate_key_format
from seo_advisor.indexnow.runner import run_submission
from seo_advisor.indexnow.validator import IndexNowScope, InvalidIndexNowScopeError, is_url_in_scope

indexnow_app = typer.Typer(help="IndexNow 發布整合：通知 Bing/Yandex 等搜尋引擎主動重新抓取")
key_app = typer.Typer(help="IndexNow key 的產生與格式驗證")
indexnow_app.add_typer(key_app, name="key")
console = Console()

_DEFAULT_MAX_URLS = 500
_DEFAULT_BATCH_SIZE = 1000


def _build_submit_confirmation(site_host: str, url_count: int) -> str:
    return f"SUBMIT INDEXNOW {site_host} {url_count}"


@key_app.command("generate")
def key_generate(
    out: str = typer.Option(None, "--out", help="把產生的 key 寫入這個檔案（省略則只印在畫面上）"),
) -> None:
    """產生一組符合 IndexNow 協定格式的隨機 key。"""
    key = generate_key()
    if out:
        Path(out).write_text(key, encoding="utf-8")
        console.print(f"[bold green]已產生 key 並寫入 {out}[/bold green]")
        console.print(
            f"接下來請把這個檔案上傳到網站根目錄（或你指定的 keyLocation 目錄），"
            f"確保 https://<你的網域>/{Path(out).name} 可以公開讀取，內容需完全等於 key 本身。"
        )
    else:
        console.print(key)


@key_app.command("check")
def key_check(key: str = typer.Argument(..., help="要驗證格式的 key 字串")) -> None:
    """檢查 key 字串是否符合 IndexNow 協定格式（8-128 字元，英數字與連字號）。"""
    try:
        validate_key_format(key)
    except InvalidIndexNowKeyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print("[bold green]格式正確。[/bold green]")


@indexnow_app.command("submit")
def submit(
    site: str = typer.Option(..., "--site", help="網站首頁網址（用於顯示，實際 host 由 --key-location 決定）"),
    url: list[str] = typer.Option(None, "--url", help="要提交的 URL（可重複指定多次）"),
    urls_file: str = typer.Option(None, "--urls-file", help="每行一個 URL 的文字檔路徑"),
    key_env: str = typer.Option(None, "--key-env", help="從這個環境變數讀取 key"),
    key_file: str = typer.Option(None, "--key-file", help="從這個檔案讀取 key"),
    key_location: str = typer.Option(
        ..., "--key-location", help="key 檔案的公開網址，例如 https://example.com/abc123.txt"
    ),
    endpoint: str = typer.Option("indexnow", "--endpoint", help="API 端點：indexnow 或 bing"),
    max_urls: int = typer.Option(_DEFAULT_MAX_URLS, "--max-urls", help="單次提交最多處理的 URL 數量上限"),
    batch_size: int = typer.Option(_DEFAULT_BATCH_SIZE, "--batch-size", help="每個批次請求的 URL 數量"),
    send: bool = typer.Option(False, "--send", help="真的送出通知（預設只做驗證與預覽，不送出）"),
    confirm: str = typer.Option(None, "--confirm", help='送出時需要輸入 "SUBMIT INDEXNOW <host> <url_count>"'),
    allow_private_network: bool = typer.Option(
        False, "--allow-private-network", help="允許 --key-location 指向本機/內網位址（本機開發測試用，預設關閉避免 SSRF）"
    ),
    out: str = typer.Option("./indexnow-report", "--out", help="報告輸出目錄"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """驗證 key/URL 並（加上 --send --confirm 後）提交 URL 給 IndexNow。"""
    urls = list(url or [])
    if urls_file:
        try:
            file_urls = [
                line.strip() for line in Path(urls_file).read_text(encoding="utf-8").splitlines() if line.strip()
            ]
        except OSError as exc:
            console.print(f"[red]無法讀取 --urls-file {urls_file!r}：{exc}[/red]")
            raise typer.Exit(code=1)
        urls.extend(file_urls)

    if not urls:
        console.print("[red]沒有提供任何 URL，請使用 --url 或 --urls-file。[/red]")
        raise typer.Exit(code=1)

    key = _resolve_key(key_env=key_env, key_file=key_file)
    if key is None:
        console.print("[red]找不到 key，請提供 --key-env 或 --key-file 其中之一。[/red]")
        raise typer.Exit(code=1)

    dry_run = not send

    try:
        resolved_endpoint = resolve_endpoint(endpoint)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    try:
        scope = IndexNowScope.from_key_location(key_location)
    except InvalidIndexNowScopeError as exc:
        console.print(f"[red]keyLocation 格式不正確：{exc}[/red]")
        raise typer.Exit(code=1)
    # 確認字串綁定的數量必須是「實際會送出」的數量（scope 驗證通過、且未
    # 超過 --max-urls 上限的筆數），而不是使用者一開始輸入的總筆數——
    # 否則使用者依 dry-run 預覽複製確認字串時，數字會跟真正送出的不一致。
    truncated_urls = urls[:max_urls]
    accepted_count = sum(1 for candidate in truncated_urls if is_url_in_scope(candidate, scope))
    expected = _build_submit_confirmation(scope.host, accepted_count)

    if not dry_run:
        if not confirm or not verify_confirmation(confirm, expected):
            console.print(
                f'[red]確認字串不符或未提供。請先不加 --send 執行一次確認預覽的 URL 數量，'
                f'再加上 --send --confirm "{expected}" 才會真的送出。[/red]'
            )
            raise typer.Exit(code=1)

    try:
        result = run_submission(
            site=site,
            urls=urls,
            key=key,
            key_location=key_location,
            endpoint=resolved_endpoint,
            dry_run=dry_run,
            max_urls=max_urls,
            batch_size=batch_size,
            allow_private_network=allow_private_network,
        )
    except InvalidIndexNowKeyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    out_path = Path(out)
    out_path.mkdir(parents=True, exist_ok=True)
    json_path = out_path / "indexnow-report.json"
    md_path = out_path / "indexnow-report.md"
    json_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(result), encoding="utf-8")

    accepted = sum(1 for v in result.url_validations if v.accepted)
    rejected = len(result.url_validations) - accepted
    if result.dry_run:
        console.print("[bold cyan]這是 dry-run 預覽，尚未送出任何通知。[/bold cyan]")
        console.print(f"  - 通過 scope 驗證：{accepted} 筆")
        console.print(f"  - 被拒絕：{rejected} 筆")
        console.print(f'加上 --send --confirm "{expected}" 才會真的送出。')
    else:
        console.print("[bold green]已送出提交。[/bold green]")
        console.print(f"  - 送出：{result.submitted_count} 筆")
        console.print(f"  - 被拒絕（scope 不符，未送出）：{rejected} 筆")
        for batch in result.batches:
            console.print(f"  - 批次 {batch.batch_index}：{batch.response_status}（HTTP {batch.status_code}）")
    for note in result.notes:
        console.print(f"[yellow]提醒：{note}[/yellow]")
    console.print(f"報告：{md_path}")
    console.print(f"機器可讀資料：{json_path}")


def _resolve_key(*, key_env: str | None, key_file: str | None) -> str | None:
    if key_env:
        value = os.environ.get(key_env)
        if value:
            return value.strip()
    if key_file:
        try:
            return Path(key_file).read_text(encoding="utf-8").strip()
        except OSError:
            return None
    return None


def _render_markdown(result) -> str:
    lines = [
        f"# IndexNow 提交報告：{result.site}",
        "",
        f"- keyLocation：{result.key_location}",
        f"- endpoint：{result.endpoint}",
        f"- 模式：{'dry-run（預覽，未送出）' if result.dry_run else '已送出'}",
        f"- 已送出：{result.submitted_count} 筆",
        f"- 已略過（scope 不符）：{result.skipped_count} 筆",
        "",
        "## URL 驗證結果",
        "",
    ]
    for validation in result.url_validations[:500]:
        mark = "接受" if validation.accepted else f"拒絕（{validation.reason}）"
        lines.append(f"- `{validation.url}`：{mark}")

    if result.batches:
        lines.append("")
        lines.append("## 批次送出結果")
        lines.append("")
        for batch in result.batches:
            lines.append(
                f"- 批次 {batch.batch_index}：{batch.url_count} 筆，"
                f"{batch.response_status}（HTTP {batch.status_code}）"
            )

    if result.notes:
        lines.append("")
        lines.append("## 提醒")
        lines.append("")
        for note in result.notes:
            lines.append(f"- {note}")

    return "\n".join(lines) + "\n"
