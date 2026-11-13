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
