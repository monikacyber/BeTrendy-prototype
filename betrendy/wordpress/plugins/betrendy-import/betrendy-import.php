<?php
/**
 * Plugin Name: BeTrendy Draft Import
 * Description: Imports the approved BeTrendy snapshot into its separate WooCommerce site as drafts, in resumable batches.
 * Version: 1.0.0
 * Requires PHP: 7.4
 */
if ( ! defined( 'ABSPATH' ) ) { exit; }

final class BeTrendy_Draft_Import {
    const STATE = 'betrendy_import_state_v1';
    const LOCK = 'betrendy_import_lock_v1';
    const HOOK = 'betrendy_import_batch_v1';
    const TYPE = 'betrendy_import';
    const PAUSE = 'betrendy_import_pause_requested';
    private static $data;
    private static $owner = '';

    public static function boot() {
        add_action( 'init', array( __CLASS__, 'register_status' ) );
        add_action( self::HOOK, array( __CLASS__, 'tick' ) );
        add_action( 'rest_after_insert_' . self::TYPE, array( __CLASS__, 'command' ), 10, 3 );
        add_filter( 'rest_pre_dispatch', array( __CLASS__, 'restrict_rest' ), 10, 3 );
        add_filter( 'wp_insert_post_data', array( __CLASS__, 'private_status' ), 10, 2 );
        register_activation_hook( __FILE__, array( __CLASS__, 'activate' ) );
        register_deactivation_hook( __FILE__, array( __CLASS__, 'deactivate' ) );
    }

    public static function register_status() {
        $caps = array_fill_keys( array( 'edit_post', 'read_post', 'delete_post', 'edit_posts',
            'edit_others_posts', 'delete_posts', 'publish_posts', 'read_private_posts',
            'delete_private_posts', 'delete_published_posts', 'delete_others_posts',
            'edit_private_posts', 'edit_published_posts', 'create_posts' ), 'manage_options' );
        register_post_type( self::TYPE, array( 'label' => 'BeTrendy import status',
            'public' => false, 'publicly_queryable' => false, 'exclude_from_search' => true,
            'show_ui' => true, 'show_in_menu' => 'tools.php', 'show_in_rest' => true,
            'rest_base' => 'betrendy-import', 'rewrite' => false, 'has_archive' => false,
            'supports' => array( 'title', 'editor', 'custom-fields' ),
            'capabilities' => $caps, 'map_meta_cap' => false,
        ) );
        register_post_meta( self::TYPE, 'betrendy_import_command', array(
            'type' => 'string', 'single' => true, 'default' => '',
            'show_in_rest' => array( 'schema' => array( 'type' => 'string', 'enum' => array( '', 'run', 'resume', 'pause' ) ) ),
            'auth_callback' => static function () { return current_user_can( 'manage_options' ); },
            'sanitize_callback' => 'sanitize_key',
        ) );
    }

    public static function restrict_rest( $result, $server, $request ) {
        if ( preg_match( '~^/wp/v2/betrendy-import(?:/|$)~', $request->get_route() ) && ! current_user_can( 'manage_options' ) ) {
            return new WP_Error( 'betrendy_import_forbidden', 'Administrator access is required.', array( 'status' => 403 ) );
        }
        return $result;
    }

    public static function private_status( $data, $postarr ) {
        if ( isset( $data['post_type'] ) && self::TYPE === $data['post_type'] && 'trash' !== $data['post_status'] ) {
            $data['post_status'] = 'private';
        }
        return $data;
    }

    private static function environment( $allow_empty_currency_change = false ) {
        $host = wp_parse_url( home_url(), PHP_URL_HOST );
        if ( 'betrendy.online' !== $host ) {
            throw new RuntimeException( 'This package is restricted to the separate BeTrendy site.' );
        }
        if ( ! class_exists( 'WooCommerce' ) || ! class_exists( 'WC_Product_Simple' ) ) {
            throw new RuntimeException( 'Activate WooCommerce before starting the import.' );
        }
        if ( ! function_exists( 'betrendy_register_source_routes' ) ) {
            throw new RuntimeException( 'Activate BeTrendy Source URLs before starting the import.' );
        }
        if ( 'UAH' !== get_woocommerce_currency() && $allow_empty_currency_change ) {
            global $wpdb;
            $count = (int) $wpdb->get_var( $wpdb->prepare( "SELECT COUNT(ID) FROM {$wpdb->posts} WHERE post_type = %s", 'product' ) );
            if ( 0 === $count ) { update_option( 'woocommerce_currency', 'UAH' ); }
        }
        if ( 'UAH' !== get_woocommerce_currency() ) { throw new RuntimeException( 'The store must use UAH; currency of an existing catalogue was not changed.' ); }
    }

    private static function data() {
        if ( null !== self::$data ) { return self::$data; }
        $checksum_file = __DIR__ . '/data/checksums.php';
        if ( ! is_file( $checksum_file ) ) { throw new RuntimeException( 'Build the deployment package before activating the importer.' ); }
        $checksums = json_decode( include $checksum_file, true );
        if ( ! is_array( $checksums ) ) { throw new RuntimeException( 'Package checksums are missing.' ); }
        $all = array();
        foreach ( array( 'catalog', 'pages', 'categories', 'media-manifest', 'redirects', 'import-config' ) as $name ) {
            $file = __DIR__ . '/data/' . $name . '.php';
            if ( ! isset( $checksums[ $name . '.php' ] ) || ! is_file( $file ) || ! hash_equals( $checksums[ $name . '.php' ], hash_file( 'sha256', $file ) ) ) {
                throw new RuntimeException( 'Package data checksum failed: ' . $name );
            }
            $all[ $name ] = json_decode( include $file, true );
            if ( ! is_array( $all[ $name ] ) ) { throw new RuntimeException( 'Invalid package data: ' . $name ); }
        }
        $all['products_uk'] = array_values( array_filter( $all['catalog'], static function ( $row ) { return 'uk' === $row['language']; } ) );
        $all['pages_uk'] = array_values( array_filter( $all['pages'], static function ( $row ) { return 'uk' === $row['language']; } ) );
        $all['categories_uk'] = array_values( array_filter( $all['categories'], static function ( $row ) { return 'uk' === $row['language']; } ) );
        if ( count( $all['products_uk'] ) !== 61 || count( $all['pages_uk'] ) !== 8 ) { throw new RuntimeException( 'Unexpected snapshot size.' ); }
        $all['media'] = array();
        foreach ( $all['media-manifest'] as $item ) { $all['media'][ $item['url'] ] = $item; }
        $wanted = array();
        foreach ( $all['products_uk'] as $row ) {
            foreach ( $row['gallery'] as $url ) { $wanted[ $url ] = $row['name']; }
            foreach ( self::image_urls( $row['description_blocks'] ) as $url ) { $wanted[ $url ] = $row['name']; }
            $all['translations'][ $row['sku'] ] = array();
        }
        foreach ( $all['catalog'] as $row ) { $all['translations'][ $row['sku'] ][ $row['language'] ] = $row; }
        foreach ( $all['pages_uk'] as $row ) {
            foreach ( self::image_urls( $row['content_blocks'] ) as $url ) { $wanted[ $url ] = $row['title']; }
            if ( ! empty( $row['featured_image'] ) ) { $wanted[ $row['featured_image'] ] = $row['title']; }
        }
        $all['media_queue'] = array();
        foreach ( $wanted as $url => $label ) {
            if ( ! isset( $all['media'][ $url ] ) ) { throw new RuntimeException( 'Content image is missing from the package manifest.' ); }
            $all['media_queue'][] = array( 'url' => $url, 'label' => $label );
        }
        self::$data = $all;
        return self::$data;
    }

    private static function image_urls( $html ) {
        preg_match_all( '~https://betrendy\.space/content/[^\s"\'<>]+~u', $html, $matches );
        return array_values( array_unique( array_map( static function ( $url ) { return html_entity_decode( $url, ENT_QUOTES, 'UTF-8' ); }, $matches[0] ) ) );
    }

    private static function save( $state ) {
        $state['updated_at'] = gmdate( 'c' );
        update_option( self::STATE, $state, false );
        $id = (int) get_option( 'betrendy_import_status_post', 0 );
        if ( $id && self::TYPE === get_post_type( $id ) ) {
            $summary = $state;
            unset( $summary['term_ids'] );
            wp_update_post( array( 'ID' => $id, 'post_status' => 'private',
                'post_content' => '<pre>' . esc_html( wp_json_encode( $summary, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE ) ) . '</pre>' ) );
        }
        return $state;
    }

    public static function activate() {
        if ( ! current_user_can( 'activate_plugins' ) ) { wp_die( 'Administrator access is required.' ); }
        self::register_status();
        try {
            self::environment( true );
            $data = self::data();
            $id = (int) get_option( 'betrendy_import_status_post', 0 );
            if ( ! $id || self::TYPE !== get_post_type( $id ) ) {
                $id = wp_insert_post( array( 'post_type' => self::TYPE, 'post_status' => 'private',
                    'post_title' => 'BeTrendy draft import', 'post_name' => 'betrendy-draft-import' ), true );
                if ( is_wp_error( $id ) ) { throw new RuntimeException( $id->get_error_message() ); }
                update_option( 'betrendy_import_status_post', $id, false );
            }
            $state = get_option( self::STATE, array() );
            if ( empty( $state ) ) {
                $state = array( 'status' => 'queued', 'phase' => 'categories', 'index' => 0,
                    'created' => array( 'media' => 0, 'products' => 0, 'pages' => 0 ),
                    'totals' => array( 'categories' => count( $data['categories_uk'] ), 'media' => count( $data['media_queue'] ), 'products' => 61, 'pages' => 8 ),
                    'term_ids' => array(), 'error' => '', 'started_at' => gmdate( 'c' ) );
                self::save( $state );
            }
            // Reactivation never silently resumes an error or restarts a completed import.
            if ( in_array( $state['status'], array( 'queued', 'running' ), true ) ) { self::schedule(); }
        } catch ( Throwable $error ) { wp_die( esc_html( $error->getMessage() ) ); }
    }

    public static function deactivate() { wp_clear_scheduled_hook( self::HOOK ); }

    private static function schedule() {
        if ( ! wp_next_scheduled( self::HOOK ) ) { wp_schedule_single_event( time() + 5, self::HOOK ); }
    }

    public static function command( $post, $request, $creating ) {
        if ( ! current_user_can( 'manage_options' ) || $post->ID !== (int) get_option( 'betrendy_import_status_post' ) ) { return; }
        $meta = $request->get_param( 'meta' );
        $command = is_array( $meta ) && isset( $meta['betrendy_import_command'] ) ? $meta['betrendy_import_command'] : '';
        if ( ! in_array( $command, array( 'pause', 'resume', 'run' ), true ) ) { return; }
        update_post_meta( $post->ID, 'betrendy_import_command', '' );
        $state = get_option( self::STATE, array() );
        if ( empty( $state ) || 'complete' === $state['status'] ) { return; }
        if ( 'pause' === $command ) {
            update_option( self::PAUSE, true, false );
            if ( ! get_option( self::LOCK ) ) {
                $state['status'] = 'paused'; $state['error'] = 'Paused by administrator.'; self::save( $state );
            }
            wp_clear_scheduled_hook( self::HOOK ); return;
        }
        if ( 'resume' === $command ) {
            delete_option( self::PAUSE );
            if ( get_option( self::LOCK ) ) { return; }
            $state['status'] = 'queued'; $state['error'] = ''; self::save( $state );
        }
        // An authenticated run processes exactly one bounded batch. Paused jobs require resume.
        self::tick();
    }

    private static function lock() {
        $old = get_option( self::LOCK );
        if ( is_array( $old ) && (int) $old['time'] < time() - 300 ) { delete_option( self::LOCK ); }
        self::$owner = wp_generate_uuid4();
        return add_option( self::LOCK, array( 'time' => time(), 'owner' => self::$owner ), '', false );
    }

    private static function unlock() {
        $lock = get_option( self::LOCK );
        if ( is_array( $lock ) && $lock['owner'] === self::$owner ) { delete_option( self::LOCK ); }
        self::$owner = '';
    }

    public static function fatal_checkpoint() {
        if ( ! self::$owner ) { return; }
        $last = error_get_last();
        if ( $last && in_array( $last['type'], array( E_ERROR, E_PARSE, E_CORE_ERROR, E_COMPILE_ERROR ), true ) ) {
            $state = get_option( self::STATE, array() );
            if ( $state ) { $state['status'] = 'paused'; $state['error'] = 'PHP stopped the batch. Inspect the server log, then resume; completed items remain saved.'; self::save( $state ); }
            wp_clear_scheduled_hook( self::HOOK );
        }
        self::unlock();
    }

    public static function tick() {
        $state = get_option( self::STATE, array() );
        if ( ! $state || ! in_array( $state['status'], array( 'queued', 'running' ), true ) || ! self::lock() ) { return; }
        register_shutdown_function( array( __CLASS__, 'fatal_checkpoint' ) );
        try {
            self::environment();
            $data = self::data();
            $state['status'] = 'running'; $state['error'] = ''; self::save( $state );
            $start = microtime( true );
            $phase = $state['phase']; $limit = 'media' === $phase ? 4 : 2;
            for ( $n = 0; $n < $limit && microtime( true ) - $start < 12; ++$n ) {
                if ( get_option( self::PAUSE ) ) {
                    $state['status'] = 'paused'; $state['error'] = 'Paused by administrator.'; self::save( $state );
                    wp_clear_scheduled_hook( self::HOOK ); break;
                }
                $state = self::one( $state, $data );
                self::save( $state );
                if ( 'complete' === $state['status'] || $phase !== $state['phase'] ) { break; }
            }
            if ( 'running' === $state['status'] ) { self::schedule(); }
        } catch ( Throwable $error ) {
            $state = get_option( self::STATE, $state );
            $state['status'] = 'paused'; $state['error'] = $error->getMessage();
            self::save( $state ); wp_clear_scheduled_hook( self::HOOK );
        } finally { self::unlock(); }
    }

    private static function one( $state, $data ) {
        $phase = $state['phase']; $index = (int) $state['index'];
        if ( 'categories' === $phase ) {
            if ( isset( $data['categories_uk'][ $index ] ) ) {
                $row = $data['categories_uk'][ $index ];
                $state['term_ids'][ $row['slug'] ] = self::category( $row ); ++$state['index'];
            } else {
                foreach ( $data['categories_uk'] as $row ) {
                    if ( ! empty( $row['parent_slug'] ) ) {
                        if ( ! isset( $state['term_ids'][ $row['parent_slug'] ] ) ) { throw new RuntimeException( 'Missing parent category.' ); }
                        $result = wp_update_term( $state['term_ids'][ $row['slug'] ], 'product_cat', array( 'parent' => $state['term_ids'][ $row['parent_slug'] ] ) );
                        if ( is_wp_error( $result ) ) { throw new RuntimeException( $result->get_error_message() ); }
                    }
                }
                $state['phase'] = 'media'; $state['index'] = 0;
            }
        } elseif ( 'media' === $phase ) {
            if ( isset( $data['media_queue'][ $index ] ) ) {
                $row = $data['media_queue'][ $index ];
                if ( self::import_media( $row['url'], $row['label'], $data ) ) { ++$state['created']['media']; }
                ++$state['index'];
            } else { $state['phase'] = 'products'; $state['index'] = 0; }
        } elseif ( 'products' === $phase ) {
            if ( isset( $data['products_uk'][ $index ] ) ) {
                if ( self::product( $data['products_uk'][ $index ], $state['term_ids'], $data ) ) { ++$state['created']['products']; }
                ++$state['index'];
            } else { $state['phase'] = 'pages'; $state['index'] = 0; }
        } elseif ( 'pages' === $phase ) {
            if ( isset( $data['pages_uk'][ $index ] ) ) {
                if ( self::page( $data['pages_uk'][ $index ] ) ) { ++$state['created']['pages']; }
                ++$state['index'];
            } else { $state['phase'] = 'finalize'; $state['index'] = 0; }
        } elseif ( 'finalize' === $phase ) {
            update_option( 'betrendy_translation_archive', array( 'pages' => $data['pages'], 'catalog' => $data['catalog'] ), false );
            $redirects = get_option( 'betrendy_source_redirects', array() );
            foreach ( $data['redirects'] as $row ) {
                $from = wp_parse_url( $row['from'], PHP_URL_PATH ); $to = wp_parse_url( $row['to'], PHP_URL_PATH );
                if ( ! preg_match( '~^/(ru|en)/~', $from ) ) { $redirects[ $from ] = $to; }
            }
            update_option( 'betrendy_source_redirects', $redirects, false );
            betrendy_register_source_routes(); flush_rewrite_rules( false );
            $state['status'] = 'complete'; $state['completed_at'] = gmdate( 'c' );
            $state['note'] = 'Imported drafts only. RU/EN data are archived but /ru/ and /en/ storefronts do not exist yet; language links must not be published until configured. Checkout, publishing and the front page still require configuration.';
            wp_clear_scheduled_hook( self::HOOK );
        } else { throw new RuntimeException( 'Unknown import phase.' ); }
        return $state;
    }

    private static function route( $path, $query ) {
        $routes = get_option( 'betrendy_source_routes', array() );
        if ( isset( $routes[ $path ] ) && $routes[ $path ] !== $query ) { throw new RuntimeException( 'An existing source route conflicts with ' . $path ); }
        $routes[ $path ] = $query; update_option( 'betrendy_source_routes', $routes, false );
    }

    private static function category( $row ) {
        $path = wp_parse_url( $row['source_url'], PHP_URL_PATH );
        $term = get_term_by( 'slug', $row['slug'], 'product_cat' );
        if ( $term ) {
            if ( get_term_meta( $term->term_id, '_betrendy_source_path', true ) !== $path ) { throw new RuntimeException( 'Unrelated category conflicts with ' . $row['slug'] ); }
            $id = (int) $term->term_id;
        } else {
            $result = wp_insert_term( $row['name'], 'product_cat', array( 'slug' => $row['slug'], 'description' => wp_kses_post( $row['description'] ) ) );
            if ( is_wp_error( $result ) ) { throw new RuntimeException( $result->get_error_message() ); }
            $id = (int) $result['term_id']; update_term_meta( $id, '_betrendy_source_path', $path );
        }
        self::route( $path, 'index.php?product_cat=' . $row['slug'] ); return $id;
    }

    private static function attachment_id( $url ) {
        $map = get_option( 'betrendy_source_media', array() );
        if ( isset( $map[ $url ] ) && get_post( $map[ $url ] ) ) {
            $id = (int) $map[ $url ];
            if ( 'attachment' !== get_post_type( $id ) || get_post_meta( $id, '_betrendy_source_url', true ) !== $url ) { throw new RuntimeException( 'An existing attachment mapping is unrelated.' ); }
            return $id;
        }
        $ids = get_posts( array( 'post_type' => 'attachment', 'post_status' => 'any', 'fields' => 'ids', 'numberposts' => 1,
            'meta_key' => '_betrendy_source_url', 'meta_value' => $url ) );
        if ( $ids ) { $map[ $url ] = (int) $ids[0]; update_option( 'betrendy_source_media', $map, false ); return (int) $ids[0]; }
        return 0;
    }

    private static function import_media( $url, $label, $data ) {
        if ( self::attachment_id( $url ) ) { return false; }
        $item = $data['media'][ $url ];
        if ( ! preg_match( '~^assets/[a-f0-9]{14}\.(?:jpe?g|png|webp|gif|svg|avif)$~', $item['path'] ) || ! preg_match( '/^[a-f0-9]{64}$/', $item['sha256'] ) ) { throw new RuntimeException( 'Invalid media path or checksum.' ); }
        $path = false;
        for ( $pack = 1; $pack <= 4; ++$pack ) {
            $base = realpath( WP_PLUGIN_DIR . '/betrendy-media-' . $pack . '/assets' );
            $candidate = $base ? realpath( $base . '/' . basename( $item['path'] ) ) : false;
            if ( $candidate && strpos( $candidate, $base . DIRECTORY_SEPARATOR ) === 0 && is_file( $candidate ) && hash_equals( $item['sha256'], hash_file( 'sha256', $candidate ) ) ) { $path = $candidate; break; }
        }
        require_once ABSPATH . 'wp-admin/includes/file.php'; require_once ABSPATH . 'wp-admin/includes/media.php'; require_once ABSPATH . 'wp-admin/includes/image.php';
        if ( $path ) {
            $temp = wp_tempnam( basename( $path ) );
            if ( ! $temp || ! copy( $path, $temp ) ) { throw new RuntimeException( 'Could not create a temporary media copy.' ); }
        } else {
            $commit = $data['import-config']['github_commit'] ?? '';
            if ( ! is_string( $commit ) || ! preg_match( '/^[a-f0-9]{40}$/', $commit ) ) { throw new RuntimeException( 'Set the immutable GitHub media commit in import-config.json before resuming.' ); }
            $remote = 'https://raw.githubusercontent.com/monikacyber/BeTrendy-prototype/' . $commit . '/betrendy/' . $item['path'];
            // The host, repository, path prefix and immutable commit are fixed; never fetch the live shop.
            $temp = wp_tempnam( basename( $item['path'] ) );
            if ( ! $temp ) { throw new RuntimeException( 'Could not allocate a temporary media file.' ); }
            $response = wp_safe_remote_get( $remote, array( 'timeout' => 45, 'redirection' => 0,
                'stream' => true, 'filename' => $temp, 'limit_response_size' => (int) $item['bytes'] + 1 ) );
            if ( is_wp_error( $response ) || 200 !== wp_remote_retrieve_response_code( $response ) ) {
                @unlink( $temp ); throw new RuntimeException( 'Could not fetch archived image ' . basename( $item['path'] ) . ' from its immutable GitHub commit.' );
            }
        }
        if ( ! is_file( $temp ) || ! hash_equals( $item['sha256'], hash_file( 'sha256', $temp ) ) ) {
            @unlink( $temp ); throw new RuntimeException( 'Archived image checksum mismatch: ' . basename( $item['path'] ) );
        }
        $id = media_handle_sideload( array( 'name' => basename( $item['path'] ), 'tmp_name' => $temp ), 0, $label );
        if ( is_wp_error( $id ) ) { @unlink( $temp ); throw new RuntimeException( $id->get_error_message() ); }
        update_post_meta( $id, '_betrendy_source_url', $url ); update_post_meta( $id, '_wp_attachment_image_alt', $label );
        $map = get_option( 'betrendy_source_media', array() ); $map[ $url ] = $id; update_option( 'betrendy_source_media', $map, false );
        return true;
    }

    private static function html( $html ) {
        $html = preg_replace_callback( '~https://betrendy\.space/content/[^\s"\'<>]+~u', static function ( $match ) {
            $url = html_entity_decode( $match[0], ENT_QUOTES, 'UTF-8' ); $id = self::attachment_id( $url );
            if ( ! $id ) { throw new RuntimeException( 'Content image was not imported yet.' ); }
            return wp_get_attachment_url( $id );
        }, $html );
        return preg_replace( '~https://betrendy\.space/(?!content/)~', trailingslashit( home_url() ), $html );
    }

    private static function product( $row, $term_ids, $data ) {
        $id = wc_get_product_id_by_sku( $row['sku'] ); $path = wp_parse_url( $row['source_url'], PHP_URL_PATH );
        if ( $id ) {
            if ( get_post_meta( $id, '_betrendy_source_url', true ) !== $row['source_url'] ) { throw new RuntimeException( 'Unrelated product conflicts with SKU ' . $row['sku'] ); }
            self::route( $path, 'index.php?post_type=product&p=' . $id ); return false;
        }
        if ( 'UAH' !== $row['currency'] ) { throw new RuntimeException( 'Unexpected product currency.' ); }
        $product = new WC_Product_Simple();
        $product->set_name( $row['name'] ); $product->set_slug( $row['slug'] ); $product->set_sku( $row['sku'] ); $product->set_status( 'draft' );
        $product->set_description( self::html( $row['description_blocks'] ) ); $product->set_short_description( $row['short_description'] );
        $product->set_regular_price( $row['regular_price'] ); $product->set_sale_price( $row['sale_price'] );
        $product->set_manage_stock( false ); $product->set_stock_status( $row['stock_status'] );
        foreach ( $row['category_slugs'] as $slug ) { if ( ! isset( $term_ids[ $slug ] ) ) { throw new RuntimeException( 'A product category was not imported.' ); } }
        $product->set_category_ids( array_values( array_intersect_key( $term_ids, array_flip( $row['category_slugs'] ) ) ) );
        if ( method_exists( $product, 'set_global_unique_id' ) && ! empty( $row['gtin'] ) ) { $product->set_global_unique_id( $row['gtin'] ); }
        $images = array();
        foreach ( $row['gallery'] as $url ) { $image = self::attachment_id( $url ); if ( ! $image ) { throw new RuntimeException( 'Product gallery is incomplete.' ); } $images[] = $image; }
        if ( $images ) { $product->set_image_id( array_shift( $images ) ); $product->set_gallery_image_ids( $images ); }
        foreach ( array( '_betrendy_source_url' => $row['source_url'], '_betrendy_source_path' => $path,
            '_betrendy_captured_date' => $row['captured_date'], '_betrendy_translations' => $data['translations'][ $row['sku'] ],
            '_betrendy_seo_title' => $row['seo_title'], '_betrendy_seo_description' => $row['seo_description'] ) as $key => $value ) { $product->update_meta_data( $key, $value ); }
        $id = $product->save();
        if ( ! $id ) { throw new RuntimeException( 'WooCommerce did not save the draft product.' ); }
        self::route( $path, 'index.php?post_type=product&p=' . $id ); return true;
    }

    private static function page( $row ) {
        $path = wp_parse_url( $row['source_url'], PHP_URL_PATH );
        $ids = get_posts( array( 'post_type' => array( 'page', 'post' ), 'post_status' => 'any', 'numberposts' => 1, 'fields' => 'ids',
            'meta_key' => '_betrendy_source_url', 'meta_value' => $row['source_url'] ) );
        $created = false;
        if ( $ids ) { $id = (int) $ids[0]; }
        else {
            $conflict = get_page_by_path( $row['slug'], OBJECT, array( 'page', 'post' ) );
            if ( $conflict ) { throw new RuntimeException( 'Unrelated page or post conflicts with ' . $row['slug'] ); }
            $id = wp_insert_post( array( 'post_type' => $row['type'], 'post_status' => 'draft', 'post_title' => $row['title'],
                'post_name' => $row['slug'], 'post_content' => self::html( $row['content_blocks'] ),
                'meta_input' => array( '_betrendy_source_url' => $row['source_url'], '_betrendy_source_path' => $path,
                    '_betrendy_seo_title' => $row['seo_title'], '_betrendy_seo_description' => $row['seo_description'] ) ), true );
            if ( is_wp_error( $id ) ) { throw new RuntimeException( $id->get_error_message() ); }
            $created = true;
        }
        if ( $created && ! empty( $row['featured_image'] ) ) { $cover = self::attachment_id( $row['featured_image'] ); if ( ! $cover ) { throw new RuntimeException( 'Article cover is missing.' ); } set_post_thumbnail( $id, $cover ); }
        if ( '/' !== $path ) { self::route( $path, 'index.php?' . ( 'page' === $row['type'] ? 'page_id=' : 'p=' ) . $id ); }
        return $created;
    }
}
BeTrendy_Draft_Import::boot();
