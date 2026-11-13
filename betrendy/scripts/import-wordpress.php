<?php
/**
 * Import the Ukrainian BeTrendy snapshot as editable WordPress/WooCommerce drafts.
 * Usage: wp eval-file import-wordpress.php /absolute/path/to/betrendy EXPECTED_SITE_URL
 * Uses local original images. Re-running skips existing source records and SKUs.
 */
if ( ! defined( 'WP_CLI' ) || ! WP_CLI ) { exit( 'Run with WP-CLI.' ); }
if ( count( $args ) !== 2 ) { WP_CLI::error( 'Supply package directory and exact target site URL.' ); }
$root = realpath( $args[0] );
$expected = untrailingslashit( $args[1] );
if ( ! $root || untrailingslashit( home_url() ) !== $expected ) {
    WP_CLI::error( 'Target site URL does not match. Nothing imported.' );
}
if ( ! in_array( wp_parse_url( $expected, PHP_URL_HOST ), array( 'snow-anteater-890728.hostingersite.com', 'betrendy.online' ), true ) ) {
    WP_CLI::error( 'This package is restricted to the separate BeTrendy installation.' );
}
if ( ! class_exists( 'WooCommerce' ) ) { WP_CLI::error( 'Install and activate WooCommerce first.' ); }
if ( get_woocommerce_currency() !== 'UAH' ) { WP_CLI::error( 'Set WooCommerce currency to UAH before import.' ); }
require_once ABSPATH . 'wp-admin/includes/file.php';
require_once ABSPATH . 'wp-admin/includes/media.php';
require_once ABSPATH . 'wp-admin/includes/image.php';

function bt_read_json( $path ) {
    $result = json_decode( file_get_contents( $path ), true );
    if ( ! is_array( $result ) ) { WP_CLI::error( 'Invalid data: ' . $path ); }
    return $result;
}
$catalog = bt_read_json( $root . '/data/catalog.json' );
$pages = bt_read_json( $root . '/data/pages.json' );
$categories = bt_read_json( $root . '/data/categories.json' );
$manifest = bt_read_json( $root . '/data/media-manifest.json' );
$media = array();
foreach ( $manifest as $item ) {
    if ( ! empty( $item['path'] ) ) { $media[ $item['url'] ] = $item; }
}
$attachments = get_option( 'betrendy_source_media', array() );

function bt_media( $url, $label = '' ) {
    global $root, $media, $attachments;
    if ( isset( $attachments[ $url ] ) && get_post( $attachments[ $url ] ) ) { return $attachments[ $url ]; }
    if ( ! isset( $media[ $url ] ) ) { WP_CLI::warning( 'Image absent from manifest: ' . $url ); return 0; }
    $item = $media[ $url ];
    $path = realpath( $root . '/' . $item['path'] );
    if ( ! $path || strpos( $path, $root . '/assets/' ) !== 0 || hash_file( 'sha256', $path ) !== $item['sha256'] ) {
        WP_CLI::error( 'Missing or changed local image: ' . $item['path'] );
    }
    $temp = wp_tempnam( basename( $path ) );
    copy( $path, $temp );
    $id = media_handle_sideload( array( 'name' => basename( $path ), 'tmp_name' => $temp ), 0, $label );
    if ( is_wp_error( $id ) ) { @unlink( $temp ); WP_CLI::error( $id->get_error_message() ); }
    update_post_meta( $id, '_betrendy_source_url', $url );
    update_post_meta( $id, '_wp_attachment_image_alt', $label );
    $attachments[ $url ] = $id;
    update_option( 'betrendy_source_media', $attachments, false );
    return $id;
}

function bt_localize_html( $content ) {
    $content = preg_replace_callback( '~https://betrendy\.space/content/[^\s"\'<>]+~u', function ( $match ) {
        $id = bt_media( html_entity_decode( $match[0] ) );
        return $id ? wp_get_attachment_url( $id ) : $match[0];
    }, $content );
    return str_replace( 'https://betrendy.space/', trailingslashit( home_url() ), $content );
}

$term_ids = array();
$routes = get_option( 'betrendy_source_routes', array() );
foreach ( $categories as $category ) {
    if ( $category['language'] !== 'uk' ) { continue; }
    $existing = get_term_by( 'slug', $category['slug'], 'product_cat' );
    if ( $existing ) { $term_ids[ $category['slug'] ] = $existing->term_id; continue; }
    $insert = wp_insert_term( $category['name'], 'product_cat', array(
        'slug' => $category['slug'], 'description' => wp_kses_post( $category['description'] ),
    ) );
    if ( is_wp_error( $insert ) ) { WP_CLI::error( $insert->get_error_message() ); }
    $term_ids[ $category['slug'] ] = $insert['term_id'];
    $path = wp_parse_url( $category['source_url'], PHP_URL_PATH );
    update_term_meta( $insert['term_id'], '_betrendy_source_path', $path );
    $routes[ $path ] = 'index.php?product_cat=' . $category['slug'];
}
foreach ( $categories as $category ) {
    if ( $category['language'] === 'uk' && ! empty( $category['parent_slug'] ) && isset( $term_ids[ $category['parent_slug'] ] ) ) {
        wp_update_term( $term_ids[ $category['slug'] ], 'product_cat', array( 'parent' => $term_ids[ $category['parent_slug'] ] ) );
    }
}

$translations = array();
foreach ( $catalog as $row ) { $translations[ $row['sku'] ][ $row['language'] ] = $row; }
$created_products = 0;
foreach ( $catalog as $row ) {
    if ( $row['language'] !== 'uk' ) { continue; }
    if ( wc_get_product_id_by_sku( $row['sku'] ) ) { WP_CLI::log( 'Skipped existing SKU ' . $row['sku'] ); continue; }
    if ( $row['currency'] !== 'UAH' ) { WP_CLI::error( 'Unexpected currency for ' . $row['sku'] ); }
    $product = new WC_Product_Simple();
    $product->set_name( $row['name'] );
    $product->set_slug( $row['slug'] );
    $product->set_sku( $row['sku'] );
    $product->set_status( 'draft' );
    $product->set_description( bt_localize_html( $row['description_blocks'] ) );
    $product->set_short_description( $row['short_description'] );
    $product->set_regular_price( $row['regular_price'] );
    $product->set_sale_price( $row['sale_price'] );
    $product->set_manage_stock( false );
    $product->set_stock_status( $row['stock_status'] );
    $product->set_category_ids( array_values( array_intersect_key( $term_ids, array_flip( $row['category_slugs'] ) ) ) );
    if ( method_exists( $product, 'set_global_unique_id' ) ) { $product->set_global_unique_id( $row['gtin'] ); }
    $images = array();
    foreach ( $row['gallery'] as $url ) { $id = bt_media( $url, $row['name'] ); if ( $id ) { $images[] = $id; } }
    if ( $images ) { $product->set_image_id( array_shift( $images ) ); $product->set_gallery_image_ids( $images ); }
    $product->update_meta_data( '_betrendy_source_url', $row['source_url'] );
    $product->update_meta_data( '_betrendy_source_path', wp_parse_url( $row['source_url'], PHP_URL_PATH ) );
    $product->update_meta_data( '_betrendy_captured_date', $row['captured_date'] );
    $product->update_meta_data( '_betrendy_translations', $translations[ $row['sku'] ] );
    $product->update_meta_data( '_betrendy_seo_title', $row['seo_title'] );
    $product->update_meta_data( '_betrendy_seo_description', $row['seo_description'] );
    $product_id = $product->save();
    $routes[ wp_parse_url( $row['source_url'], PHP_URL_PATH ) ] = 'index.php?post_type=product&p=' . $product_id;
    ++$created_products;
    WP_CLI::log( 'Imported draft SKU ' . $row['sku'] );
}
$created_pages = 0;
foreach ( $pages as $page ) {
    if ( $page['language'] !== 'uk' ) { continue; }
    $existing = get_posts( array( 'post_type' => array( 'page', 'post' ), 'post_status' => 'any', 'meta_key' => '_betrendy_source_url', 'meta_value' => $page['source_url'], 'numberposts' => 1 ) );
    if ( $existing ) { continue; }
    $id = wp_insert_post( array( 'post_type' => $page['type'], 'post_status' => 'draft',
        'post_title' => $page['title'], 'post_name' => $page['slug'],
        'post_content' => bt_localize_html( $page['content_blocks'] ),
        'meta_input' => array( '_betrendy_source_url' => $page['source_url'], '_betrendy_seo_title' => $page['seo_title'], '_betrendy_seo_description' => $page['seo_description'] ),
    ), true );
    if ( is_wp_error( $id ) ) { WP_CLI::error( $id->get_error_message() ); }
    ++$created_pages;
}
update_option( 'betrendy_translation_archive', array( 'pages' => $pages, 'catalog' => $catalog ), false );
update_option( 'betrendy_source_routes', $routes, false );
$redirects = array();
foreach ( bt_read_json( $root . '/data/redirects.json' ) as $redirect ) {
    $redirects[ wp_parse_url( $redirect['from'], PHP_URL_PATH ) ] = wp_parse_url( $redirect['to'], PHP_URL_PATH );
}
update_option( 'betrendy_source_redirects', $redirects, false );
flush_rewrite_rules();
WP_CLI::success( 'Created ' . $created_products . ' draft products and ' . $created_pages . ' draft pages/posts. Review, configure multilingual/currency and checkout before publishing.' );
