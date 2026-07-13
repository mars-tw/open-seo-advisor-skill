"""主外掛檔案（`<slug>.php`）的模板：WordPress plugin header + bootstrap。"""

from __future__ import annotations

from seo_advisor.plugins.models import PluginScaffoldRequest


def render_main_php(req: PluginScaffoldRequest) -> str:
    prefix = req.php_class_prefix
    constant_prefix = req.php_constant_prefix
    return f'''<?php
/**
 * Plugin Name: {req.plugin_name}
 * Plugin URI:
 * Description: {req.description}
 * Version: {req.version}
 * Author: {req.author}
 * License: {req.license}
 * Text Domain: {req.text_domain}
 * Requires at least: 5.8
 * Requires PHP: 7.4
 *
 * 由 Open SEO Advisor 產生的 scaffold，實際部署前請自行 review 與測試。
 */

// 直接存取這個檔案時拒絕執行，避免在沒有 WordPress 執行環境的情況下
// 曝露任何邏輯或錯誤訊息。
defined( 'ABSPATH' ) || exit;

define( '{constant_prefix}_VERSION', '{req.version}' );
define( '{constant_prefix}_PLUGIN_FILE', __FILE__ );
define( '{constant_prefix}_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );
define( '{constant_prefix}_PLUGIN_URL', plugin_dir_url( __FILE__ ) );

require_once {constant_prefix}_PLUGIN_DIR . 'includes/class-{req.slug}-schema.php';
require_once {constant_prefix}_PLUGIN_DIR . 'admin/class-{req.slug}-admin.php';

/**
 * 外掛啟動：掛載前台 schema 輸出與後台設定頁。用 plugins_loaded 而非
 * 直接在檔案頂層執行，確保所有 WordPress 核心 API 都已經載入完成。
 */
function {prefix.lower()}_bootstrap() {{
	$schema = new {prefix}_Schema();
	$schema->register_hooks();

	if ( is_admin() ) {{
		$admin = new {prefix}_Admin();
		$admin->register_hooks();
	}}
}}
add_action( 'plugins_loaded', '{prefix.lower()}_bootstrap' );
'''
