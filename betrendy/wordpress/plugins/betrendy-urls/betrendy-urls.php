<?php
/**
 * Plugin Name: BeTrendy Source URLs
 * Description: Preserves the imported BeTrendy product/category URLs and SEO metadata.
 * Version: 1.0.0
 */
if ( ! defined( 'ABSPATH' ) ) { exit; }

function betrendy_register_source_routes() {
    foreach ( get_option( 'betrendy_source_routes', array() ) as $path => $query ) {
        add_rewrite_rule( '^' . preg_quote( trim( $path, '/' ), '~' ) . '/?$', $query, 'top' );
        if ( strpos( $query, 'product_cat=' ) !== false ) {
            add_rewrite_rule( '^' . preg_quote( trim( $path, '/' ), '~' ) . '/page/([0-9]+)/?$', $query . '&paged=$matches[1]', 'top' );
            add_rewrite_rule( '^' . preg_quote( trim( $path, '/' ), '~' ) . '/filter/page=([0-9]+)/?$', $query . '&paged=$matches[1]', 'top' );
            add_rewrite_rule( '^' . preg_quote( trim( $path, '/' ), '~' ) . '/filter/page=all/?$', $query . '&betrendy_all=1', 'top' );
        }
    }
}
add_action( 'init', 'betrendy_register_source_routes' );
add_filter( 'query_vars', function ( $vars ) { $vars[] = 'betrendy_all'; return $vars; } );
add_action( 'pre_get_posts', function ( $query ) {
    if ( ! is_admin() && $query->is_main_query() && $query->get( 'betrendy_all' ) && $query->get( 'product_cat' ) ) {
        $query->set( 'posts_per_page', 200 );
    }
} );
register_activation_hook( __FILE__, function () {
    betrendy_register_source_routes();
    flush_rewrite_rules();
} );
add_filter( 'post_type_link', function ( $url, $post ) {
    $path = get_post_meta( $post->ID, '_betrendy_source_path', true );
    return $post->post_type === 'product' && $path ? home_url( $path ) : $url;
}, 10, 2 );
add_filter( 'post_link', function ( $url, $post ) {
    $path = get_post_meta( $post->ID, '_betrendy_source_path', true );
    return $path ? home_url( $path ) : $url;
}, 10, 2 );
add_filter( 'page_link', function ( $url, $id ) {
    $path = get_post_meta( $id, '_betrendy_source_path', true );
    return $path && $path !== '/' ? home_url( $path ) : $url;
}, 10, 2 );
add_filter( 'term_link', function ( $url, $term, $taxonomy ) {
    $path = get_term_meta( $term->term_id, '_betrendy_source_path', true );
    return $taxonomy === 'product_cat' && $path ? home_url( $path ) : $url;
}, 10, 3 );
add_filter( 'pre_get_document_title', function ( $title ) {
    $value = is_singular() ? get_post_meta( get_queried_object_id(), '_betrendy_seo_title', true ) : '';
    return $value ?: $title;
} );
add_action( 'wp_head', function () {
    if ( ! is_singular() ) { return; }
    $value = get_post_meta( get_queried_object_id(), '_betrendy_seo_description', true );
    if ( $value ) { echo '<meta name="description" content="' . esc_attr( $value ) . '">' . "\n"; }
}, 1 );
add_action( 'template_redirect', function () {
    $path = wp_parse_url( wp_unslash( $_SERVER['REQUEST_URI'] ?? '/' ), PHP_URL_PATH );
    $redirects = get_option( 'betrendy_source_redirects', array() );
    if ( isset( $redirects[ $path ] ) ) {
        wp_safe_redirect( home_url( $redirects[ $path ] ), 301 );
        exit;
    }
} );
