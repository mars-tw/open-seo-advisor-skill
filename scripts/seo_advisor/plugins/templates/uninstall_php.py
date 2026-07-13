"""`uninstall.php` 的模板：解除安裝時清理外掛新增的 options，避免殘留
資料庫垃圾資料。
"""

from __future__ import annotations

from seo_advisor.plugins.models import PluginScaffoldRequest


def render_uninstall_php(req: PluginScaffoldRequest) -> str:
    option_prefix = req.text_domain.replace("-", "_")
    return f'''<?php
/**
 * {req.plugin_name}：解除安裝時清理外掛設定，避免殘留資料庫垃圾資料。
 *
 * WordPress 只在使用者透過後台「刪除」外掛（而非單純停用）時才會執行
 * 這個檔案；WP_UNINSTALL_PLUGIN 常數的存在性檢查是官方建議的標準防護，
 * 避免這個檔案被直接存取執行。
 */

if ( ! defined( 'WP_UNINSTALL_PLUGIN' ) ) {{
	exit;
}}

delete_option( '{option_prefix}_org_name' );
delete_option( '{option_prefix}_org_logo_url' );
delete_option( '{option_prefix}_org_same_as' );
'''
