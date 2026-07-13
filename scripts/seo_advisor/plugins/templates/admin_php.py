"""後台設定頁 class 的模板：Organization 資訊設定表單。

安全設計（NORA 複審要求，不可省略）：
- 表單提交一律 `check_admin_referer()` 驗證 nonce。
- 進入設定頁與處理表單一律 `current_user_can( 'manage_options' )` 檢查。
- 所有輸入透過 `sanitize_text_field()`/`esc_url_raw()` 清洗後才寫入
  `update_option()`。
- 所有輸出透過 `esc_attr()`/`esc_html__()`/`esc_url()` 跳脫。
"""

from __future__ import annotations

from seo_advisor.plugins.models import PluginScaffoldRequest


def render_admin_php(req: PluginScaffoldRequest) -> str:
    prefix = req.php_class_prefix
    option_prefix = req.text_domain.replace("-", "_")
    nonce_action = f"{req.text_domain}_save_settings"
    nonce_field = f"{option_prefix}_nonce"
    return f'''<?php
/**
 * {req.plugin_name}：後台設定頁（Organization 結構化資料欄位）。
 */

defined( 'ABSPATH' ) || exit;

class {prefix}_Admin {{

	public function register_hooks() {{
		add_action( 'admin_menu', array( $this, 'register_settings_page' ) );
		add_action( 'admin_init', array( $this, 'maybe_save_settings' ) );
	}}

	public function register_settings_page() {{
		add_options_page(
			esc_html__( '{req.plugin_name}', '{req.text_domain}' ),
			esc_html__( '{req.plugin_name}', '{req.text_domain}' ),
			'manage_options',
			'{req.slug}',
			array( $this, 'render_settings_page' )
		);
	}}

	/**
	 * 表單提交處理：capability check 在 nonce 驗證之前先擋一次，避免
	 * 沒有權限的使用者觸發任何後續邏輯（即使 nonce 檢查本身也會失敗，
	 * 但檢查順序上權限應該優先於格式驗證）。
	 */
	public function maybe_save_settings() {{
		if ( ! isset( $_POST['{nonce_field}'] ) ) {{
			return;
		}}

		if ( ! current_user_can( 'manage_options' ) ) {{
			wp_die( esc_html__( '你沒有權限執行這個操作。', '{req.text_domain}' ) );
		}}

		check_admin_referer( '{nonce_action}', '{nonce_field}' );

		$org_name = isset( $_POST['{option_prefix}_org_name'] )
			? sanitize_text_field( wp_unslash( $_POST['{option_prefix}_org_name'] ) )
			: '';
		update_option( '{option_prefix}_org_name', $org_name );

		$org_logo_url = isset( $_POST['{option_prefix}_org_logo_url'] )
			? esc_url_raw( wp_unslash( $_POST['{option_prefix}_org_logo_url'] ) )
			: '';
		update_option( '{option_prefix}_org_logo_url', $org_logo_url );

		$same_as_raw = isset( $_POST['{option_prefix}_org_same_as'] )
			? sanitize_textarea_field( wp_unslash( $_POST['{option_prefix}_org_same_as'] ) )
			: '';
		$same_as_lines = array_filter( array_map( 'trim', explode( "\\n", $same_as_raw ) ) );
		update_option( '{option_prefix}_org_same_as', array_map( 'esc_url_raw', $same_as_lines ) );

		add_settings_error(
			'{req.slug}',
			'{req.slug}-saved',
			esc_html__( '設定已儲存。', '{req.text_domain}' ),
			'success'
		);
	}}

	public function render_settings_page() {{
		if ( ! current_user_can( 'manage_options' ) ) {{
			wp_die( esc_html__( '你沒有權限檢視這個頁面。', '{req.text_domain}' ) );
		}}

		settings_errors( '{req.slug}' );

		$org_name     = get_option( '{option_prefix}_org_name', '' );
		$org_logo_url = get_option( '{option_prefix}_org_logo_url', '' );
		$same_as      = get_option( '{option_prefix}_org_same_as', array() );
		$same_as_text = is_array( $same_as ) ? implode( "\\n", $same_as ) : '';
		?>
		<div class="wrap">
			<h1><?php echo esc_html__( '{req.plugin_name}', '{req.text_domain}' ); ?></h1>
			<form method="post">
				<?php wp_nonce_field( '{nonce_action}', '{nonce_field}' ); ?>
				<table class="form-table" role="presentation">
					<tr>
						<th scope="row">
							<label for="{option_prefix}_org_name">
								<?php echo esc_html__( '公司/組織名稱', '{req.text_domain}' ); ?>
							</label>
						</th>
						<td>
							<input type="text" id="{option_prefix}_org_name"
								name="{option_prefix}_org_name"
								value="<?php echo esc_attr( $org_name ); ?>" class="regular-text" />
						</td>
					</tr>
					<tr>
						<th scope="row">
							<label for="{option_prefix}_org_logo_url">
								<?php echo esc_html__( 'Logo 網址', '{req.text_domain}' ); ?>
							</label>
						</th>
						<td>
							<input type="url" id="{option_prefix}_org_logo_url"
								name="{option_prefix}_org_logo_url"
								value="<?php echo esc_attr( $org_logo_url ); ?>" class="regular-text" />
						</td>
					</tr>
					<tr>
						<th scope="row">
							<label for="{option_prefix}_org_same_as">
								<?php echo esc_html__( '社群/相關網址（每行一個）', '{req.text_domain}' ); ?>
							</label>
						</th>
						<td>
							<textarea id="{option_prefix}_org_same_as"
								name="{option_prefix}_org_same_as" rows="5"
								class="large-text"><?php echo esc_textarea( $same_as_text ); ?></textarea>
						</td>
					</tr>
				</table>
				<?php submit_button(); ?>
			</form>
		</div>
		<?php
	}}
}}
'''
