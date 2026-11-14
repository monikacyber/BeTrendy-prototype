<?php
/**
 * BeTrendy theme setup. Commerce remains handled by WooCommerce.
 *
 * @package BeTrendy
 */

if ( ! defined( 'ABSPATH' ) ) {
    exit;
}

add_action( 'after_setup_theme', function () {
    add_theme_support( 'wp-block-styles' );
    add_theme_support( 'editor-styles' );
    add_theme_support( 'woocommerce' );
    add_theme_support( 'wc-product-gallery-zoom' );
    add_theme_support( 'wc-product-gallery-lightbox' );
    add_theme_support( 'wc-product-gallery-slider' );
    add_editor_style( 'style.css' );
} );

add_action( 'wp_enqueue_scripts', function () {
    wp_enqueue_style( 'betrendy-style', get_stylesheet_uri(), array(), wp_get_theme()->get( 'Version' ) );
    if ( is_front_page() ) {
        wp_enqueue_script( 'betrendy-carousel', get_theme_file_uri( 'assets/carousel.js' ), array(), wp_get_theme()->get( 'Version' ), true );
    }
} );

add_action( 'enqueue_block_assets', function () {
    // Same font and provider as the source site. No tracking scripts are added.
    wp_enqueue_style(
        'betrendy-geologica',
        'https://fonts.googleapis.com/css2?family=Geologica:wght@400;700&display=swap&subset=cyrillic',
        array(),
        null
    );
} );

// The header has explicit cart/account links. Prevent WooCommerce from adding
// a second set after every separate navigation block in this block theme.
add_filter( 'hooked_block_types', function ( $types, $position, $anchor ) {
    if ( 'core/navigation' === $anchor ) {
        $types = array_values( array_diff( $types, array( 'woocommerce/customer-account', 'woocommerce/mini-cart' ) ) );
    }
    return $types;
}, 20, 3 );

// Let an authorised editor review the imported draft catalogue inside page previews.
add_filter( 'woocommerce_shortcode_products_query', function ( $query ) {
    if ( is_preview() && current_user_can( 'edit_products' ) ) {
        $query['post_status'] = array( 'publish', 'draft' );
        $query['meta_query'][] = array( 'key' => '_betrendy_source_url', 'compare' => 'EXISTS' );
    }
    return $query;
} );

add_filter( 'woocommerce_loop_product_link', function ( $link, $product ) {
    if ( is_preview() && current_user_can( 'edit_post', $product->get_id() ) && 'draft' === $product->get_status() ) {
        return get_preview_post_link( $product->get_id() );
    }
    return $link;
}, 10, 2 );
