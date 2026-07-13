"""Schema（JSON-LD 結構化資料）class 的模板：讀取 admin 設定值，在
`wp_head` 輸出 Organization/WebSite/Article JSON-LD。
"""

from __future__ import annotations

from seo_advisor.plugins.models import PluginScaffoldRequest


def render_schema_php(req: PluginScaffoldRequest) -> str:
    prefix = req.php_class_prefix
    option_prefix = req.text_domain.replace("-", "_")
    return f'''<?php
/**
 * {req.plugin_name}：前台 JSON-LD 結構化資料輸出。
 */

defined( 'ABSPATH' ) || exit;

class {prefix}_Schema {{

	/**
	 * 掛載前台輸出 hook。所有輸出邏輯都在 wp_head 內執行，不修改任何
	 * 資料庫內容——這個 class 只負責「讀取設定、產生 JSON-LD」。
	 */
	public function register_hooks() {{
		add_action( 'wp_head', array( $this, 'output_json_ld' ) );
	}}

	/**
	 * 依目前頁面類型輸出對應的 JSON-LD：首頁輸出 Organization + WebSite，
	 * 單篇文章額外輸出 Article。所有欄位一律用 esc_url_raw()/sanitize_
	 * text_field() 讀取設定值，輸出一律透過 wp_json_encode()，不手動拼接
	 * JSON 字串，避免逸出字元處理疏漏造成的 XSS 或 JSON 結構破壞。
	 */
	public function output_json_ld() {{
		$graphs = array();

		$organization = $this->build_organization_schema();
		if ( $organization ) {{
			$graphs[] = $organization;
		}}

		if ( is_front_page() ) {{
			$website = $this->build_website_schema();
			if ( $website ) {{
				$graphs[] = $website;
			}}
		}}

		if ( is_singular( 'post' ) ) {{
			$article = $this->build_article_schema();
			if ( $article ) {{
				$graphs[] = $article;
			}}
		}}

		if ( empty( $graphs ) ) {{
			return;
		}}

		$payload = array(
			'@context' => 'https://schema.org',
			'@graph'   => $graphs,
		);

		// 只在 <script type="application/ld+json"> 內放置 wp_json_encode()
		// 的輸出，不與任何其他字串拼接，避免內容意外跳出 script 標籤。
		echo '<script type="application/ld+json">' .
			wp_json_encode( $payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE ) .
			'</script>' . "\\n";
	}}

	private function build_organization_schema() {{
		$name = get_option( '{option_prefix}_org_name', '' );
		if ( empty( $name ) ) {{
			return null;
		}}

		$schema = array(
			'@type' => 'Organization',
			'name'  => sanitize_text_field( $name ),
			'url'   => esc_url_raw( home_url( '/' ) ),
		);

		$logo = get_option( '{option_prefix}_org_logo_url', '' );
		if ( ! empty( $logo ) ) {{
			$schema['logo'] = esc_url_raw( $logo );
		}}

		$same_as = get_option( '{option_prefix}_org_same_as', array() );
		if ( is_array( $same_as ) && ! empty( $same_as ) ) {{
			$schema['sameAs'] = array_map( 'esc_url_raw', $same_as );
		}}

		return $schema;
	}}

	private function build_website_schema() {{
		$name = get_bloginfo( 'name' );
		if ( empty( $name ) ) {{
			return null;
		}}

		return array(
			'@type' => 'WebSite',
			'name'  => sanitize_text_field( $name ),
			'url'   => esc_url_raw( home_url( '/' ) ),
		);
	}}

	private function build_article_schema() {{
		$post_id = get_the_ID();
		if ( ! $post_id ) {{
			return null;
		}}

		return array(
			'@type'         => 'Article',
			'headline'      => sanitize_text_field( get_the_title( $post_id ) ),
			'url'           => esc_url_raw( get_permalink( $post_id ) ),
			'datePublished' => esc_html( get_the_date( DATE_W3C, $post_id ) ),
			'dateModified'  => esc_html( get_the_modified_date( DATE_W3C, $post_id ) ),
		);
	}}
}}
'''
