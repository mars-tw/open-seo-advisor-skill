"""Plugin Dev Mode 的 CLI subapp（seo-advisor plugin dev ...）。

安全設計：純本機檔案產出，不做任何遠端寫入（不安裝到 WordPress、不呼叫
WordPress REST API、不透過 FTP/SFTP/SSH 上傳、不執行 shell_exec）。輸出
目錄若已存在且非空，預設拒絕覆蓋，需要 --force 才會覆蓋既有內容，避免
無聲蓋掉使用者可能已經手動修改過的既有 scaffold。
"""

from __future__ import annotations

from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console

from seo_advisor.errors import translate_exception
from seo_advisor.plugins.generator import PluginOutputExistsError, generate_plugin_scaffold
from seo_advisor.plugins.models import PluginScaffoldRequest

plugin_app = typer.Typer(help="Plugin Dev Mode：產生 WordPress 外掛 scaffold")
console = Console()


@plugin_app.command("dev")
def dev(
    cms: str = typer.Option("wordpress", "--cms", help="目標 CMS（目前只支援 wordpress）"),
    feature: str = typer.Option(..., "--feature", help="要產生的功能（目前只支援 schema-generator）"),
    name: str = typer.Option(..., "--name", help="外掛顯示名稱，例如 'Open SEO Schema Helper'"),
    slug: str = typer.Option(..., "--slug", help="外掛 slug（小寫英數字與連字號），用來衍生檔名/PHP class 名稱"),
    description: str = typer.Option("", "--description", help="外掛描述"),
    author: str = typer.Option("Open SEO Advisor", "--author", help="作者名稱"),
    version: str = typer.Option("0.1.0", "--plugin-version", help="外掛版本號"),
    license_: str = typer.Option("GPL-2.0-or-later", "--license", help="授權條款"),
    zip_output: bool = typer.Option(True, "--zip/--no-zip", help="是否額外打包成 zip（預設開啟）"),
    out: str = typer.Option("./plugin-dev", "--out", help="輸出目錄"),
    force: bool = typer.Option(False, "--force", help="輸出目錄已存在且非空時，是否覆蓋既有內容"),
    debug: bool = typer.Option(False, "--debug", help="發生錯誤時顯示完整技術細節"),
) -> None:
    """產生一份可審閱、可自行部署的 WordPress 外掛 scaffold（不會自動安裝或啟用）。"""
    try:
        req = PluginScaffoldRequest(
            cms=cms,
            feature=feature,
            plugin_name=name,
            slug=slug,
            description=description,
            author=author,
            version=version,
            license=license_,
            zip_output=zip_output,
        )
    except ValidationError as exc:
        console.print(f"[red]參數不合法：{exc}[/red]")
        raise typer.Exit(code=1)

    try:
        result = generate_plugin_scaffold(req, out_dir=out, force=force)
    except PluginOutputExistsError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    except Exception as exc:  # noqa: BLE001
        if debug:
            raise
        console.print(f"[red]{translate_exception(exc).render()}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold green]完成！已產生 {req.plugin_name} 的 scaffold。[/bold green]")
    console.print(f"外掛目錄：{result.plugin_dir}")
    if result.zip_path:
        console.print(f"zip 打包：{result.zip_path}")
    console.print(
        "[yellow]提醒：這是自動產生的 scaffold，請先在 staging/測試站台安裝並完整測試，"
        "自行 review 程式碼、依你的站台需求調整，確認無誤後才部署到正式站台。[/yellow]"
    )
    console.print(f"共寫出 {len(result.written_files)} 個檔案：")
    for path in result.written_files:
        console.print(f"  - {Path(path).name}")
