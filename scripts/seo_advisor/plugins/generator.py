"""WordPress 外掛 scaffold 產生：組裝模板、寫出檔案、選配打包成 zip。

MVP 只支援 `schema-generator` feature；純本機檔案產出，不做任何遠端
寫入、不呼叫任何外部 API、不修改使用者現有的 WordPress 站台——這個
工具唯一的動作是在 `--out` 指定的本機目錄下建立新檔案。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from seo_advisor.plugins.models import (
    PluginScaffoldRequest,
    PluginScaffoldResult,
    WordPressPluginFeature,
    resolve_output_dir,
)
from seo_advisor.plugins.templates.admin_php import render_admin_php
from seo_advisor.plugins.templates.main_php import render_main_php
from seo_advisor.plugins.templates.readme_txt import render_readme_txt
from seo_advisor.plugins.templates.schema_php import render_schema_php
from seo_advisor.plugins.templates.uninstall_php import render_uninstall_php


class PluginOutputExistsError(FileExistsError):
    """輸出目錄已存在且非空、未指定 --force 時拋出。"""


def _files_for_request(req: PluginScaffoldRequest) -> dict[str, str]:
    """回傳 {相對於 plugin 目錄的路徑: 檔案內容}。目前 MVP 只有
    schema-generator 一種 feature，未來新增 feature 時應在這裡依
    `req.feature` 分支組裝不同的檔案集合。
    """
    if req.feature != WordPressPluginFeature.SCHEMA_GENERATOR:
        raise NotImplementedError(f"目前只支援 {WordPressPluginFeature.SCHEMA_GENERATOR.value} feature。")

    return {
        f"{req.slug}.php": render_main_php(req),
        f"includes/class-{req.slug}-schema.php": render_schema_php(req),
        f"admin/class-{req.slug}-admin.php": render_admin_php(req),
        "readme.txt": render_readme_txt(req),
        "uninstall.php": render_uninstall_php(req),
    }


def generate_plugin_scaffold(
    req: PluginScaffoldRequest, *, out_dir: str, force: bool = False
) -> PluginScaffoldResult:
    """產生 scaffold 到 `<out_dir>/<slug>/`，選配打包成 zip。

    force=False（預設）時，若輸出目錄已存在且非空會拒絕執行，避免無聲
    覆蓋使用者可能已經手動修改過的既有 scaffold。
    """
    plugin_dir = resolve_output_dir(out_dir, req.slug)

    if plugin_dir.exists() and any(plugin_dir.iterdir()) and not force:
        raise PluginOutputExistsError(
            f"輸出目錄 {plugin_dir} 已存在且非空。加上 --force 才會覆蓋既有內容。"
        )

    files = _files_for_request(req)

    written_files: list[str] = []
    for relative_path, content in files.items():
        target = plugin_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        written_files.append(str(target))

    zip_path: str | None = None
    if req.zip_output:
        zip_path = str(plugin_dir.parent / f"{req.slug}.zip")
        _build_zip(plugin_dir, req.slug, zip_path)

    return PluginScaffoldResult(
        plugin_dir=str(plugin_dir),
        written_files=written_files,
        zip_path=zip_path,
    )


def _build_zip(plugin_dir: Path, slug: str, zip_path: str) -> None:
    """把 `plugin_dir` 底下的所有檔案打包進 zip，zip 內的路徑一律是
    `<slug>/<relative_path>`（相對路徑、不含 `..`），確保之後解壓縮時
    會產生一個乾淨的 `<slug>/` 目錄，不會有路徑逸出 zip 根目錄的風險。
    """
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(plugin_dir.rglob("*")):
            if not file_path.is_file():
                continue
            arcname = f"{slug}/{file_path.relative_to(plugin_dir).as_posix()}"
            zf.write(file_path, arcname=arcname)
